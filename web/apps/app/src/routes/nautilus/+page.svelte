<script lang="ts">
	import type { PageData } from './$types';
	import type { NautilusTrade, AccountSnapshot } from '$lib/types';
	import { fmtPct, fmtTime, fmtUSD } from '$lib/utils';
	import { t, type Lang } from '$lib/i18n';
	import { resolve } from '$app/paths';

	let { data }: { data: PageData } = $props();
	const lang = $derived<Lang>((data as { lang?: Lang }).lang ?? 'zh');
	const trades = $derived<NautilusTrade[]>(data.trades ?? []);
	const snapshots = $derived<AccountSnapshot[]>(
		(data as { snapshots?: AccountSnapshot[] }).snapshots ?? []
	);
	// One curve per account; render once >=2 points exist, else an honest "accumulating" note.
	const snapByAccount = $derived.by(() => {
		const m: Record<string, AccountSnapshot[]> = {};
		for (const s of snapshots) (m[s.account] ??= []).push(s);
		return Object.entries(m);
	});
	function curvePath(pts: AccountSnapshot[], w = 560, h = 90, pad = 8): string {
		const vals = pts.map((p) => p.net_liq);
		const lo = Math.min(...vals);
		const hi = Math.max(...vals);
		const span = hi - lo || 1;
		return pts
			.map((p, i) => {
				const x = pad + (i / Math.max(1, pts.length - 1)) * (w - pad * 2);
				const y = pad + (1 - (p.net_liq - lo) / span) * (h - pad * 2);
				return `${x.toFixed(1)},${y.toFixed(1)}`;
			})
			.join(' ');
	}
	// A node restart re-registers a position as a new row; migration 032 closes the stale copy
	// with exit_reason='superseded' and no exit price/PnL. It is never an open position and
	// never a real close, so it renders with a neutral label instead of numbers.
	const isSuperseded = (x: NautilusTrade) => x.exit_reason === 'superseded';
	const open = $derived(trades.filter((x) => !x.close_date && !isSuperseded(x)));
	const closed = $derived(trades.filter((x) => x.close_date || isSuperseded(x)));
	const nSuperseded = $derived(closed.filter(isSuperseded).length);

	const tr = (zh: string, en: string) => (lang === 'zh' ? zh : en);
	const metaDesc = $derived(
		tr(
			'公开账本：实时持仓与不可伪造的每日净值。',
			'Public ledger: live positions and an unfakeable daily NetLiq.'
		)
	);

	function pnlClass(v: number | null | undefined) {
		if (v == null) return 'text-muted-foreground';
		return v > 0 ? 'text-green-400' : v < 0 ? 'text-red-400' : 'text-muted-foreground';
	}
</script>

<svelte:head>
	<title>{tr('Nautilus 执行引擎', 'Nautilus engine')}</title>
	<meta name="description" content={metaDesc} />
	<meta property="og:title" content={tr('Nautilus 执行引擎', 'Nautilus engine')} />
	<meta property="og:description" content={metaDesc} />
</svelte:head>

<div class="mx-auto w-full max-w-5xl px-4 py-6">
	<div class="mb-4 flex items-center gap-3">
		<h1 class="text-xl font-semibold text-foreground">
			{tr('Nautilus 执行引擎', 'Nautilus engine')}
		</h1>
		{#if trades.length}
			{@const envs = [...new Set(trades.map((t) => t.environment))]}
			{#each envs as e (e)}
				<span
					class="rounded-full border px-2 py-0.5 font-mono text-[11px] uppercase {e === 'live'
						? 'border-red-700/50 bg-red-950/40 text-red-300'
						: 'border-yellow-700/50 bg-yellow-950/40 text-yellow-300'}">{e}</span
				>
			{/each}
		{/if}
	</div>
	<p class="mb-2 text-xs text-muted-foreground">
		{tr(
			'NautilusTrader 实时持仓(累积器 + Donchian 趋势),独立于 freqtrade 的成交流。',
			'Live positions from the NautilusTrader engine (accumulator + Donchian trend), separate from the freqtrade feed.'
		)}
	</p>
	<p class="mb-6 text-xs text-muted-foreground">
		{t(lang, 'nautilus.recordLink')}
		<a href={resolve('/record')} class="font-medium text-primary hover:underline"
			>{t(lang, 'nautilus.recordCta')}</a
		>
	</p>

	<!-- Verifiable real-account equity curve: daily NetLiq snapshots, platform-recorded
	     (screenshots can be faked; this series cannot). -->
	<section class="mb-6 rounded-xl border bg-card p-4">
		<div class="mb-1 flex items-baseline justify-between">
			<h2 class="text-sm font-semibold text-foreground">
				{tr('真实账户净值(每日快照)', 'Real account NetLiq (daily snapshots)')}
			</h2>
			<span class="text-[10px] text-muted-foreground uppercase">
				{tr('平台自动记录 · 不可伪造', 'platform-recorded · unfakeable')}
			</span>
		</div>
		{#if snapshots.length === 0}
			<p class="text-xs text-muted-foreground">
				{tr(
					'快照服务已启动,首个数据点今晚记录。',
					'Snapshot service armed; first point lands tonight.'
				)}
			</p>
		{:else}
			{#each snapByAccount as [account, pts] (account)}
				<div class="mt-2">
					<div class="flex items-baseline justify-between text-xs">
						<span class="font-mono text-muted-foreground">{account} · {pts[0].environment}</span>
						<span class="font-mono text-foreground tabular-nums">
							{pts[pts.length - 1].net_liq.toLocaleString(undefined, { maximumFractionDigits: 0 })}
							{pts[pts.length - 1].currency}
							{#if pts.length >= 2}
								{@const chg = (pts[pts.length - 1].net_liq / pts[0].net_liq - 1) * 100}
								<span class={chg >= 0 ? 'text-green-400' : 'text-red-400'}>
									({chg >= 0 ? '+' : ''}{chg.toFixed(2)}%)
								</span>
							{/if}
						</span>
					</div>
					{#if pts.length >= 2}
						<svg viewBox="0 0 560 90" class="mt-1 h-[90px] w-full">
							<polyline
								points={curvePath(pts)}
								fill="none"
								stroke={pts[pts.length - 1].net_liq >= pts[0].net_liq
									? 'rgb(74 222 128)'
									: 'rgb(248 113 113)'}
								stroke-width="1.5"
							/>
						</svg>
						<div class="flex justify-between text-[10px] text-muted-foreground">
							<span>{pts[0].snap_date}</span><span>{pts[pts.length - 1].snap_date}</span>
						</div>
					{:else}
						<p class="mt-1 text-xs text-muted-foreground">
							{tr(
								`第 1 天 · 每天 09:07 自动记录,攒够两个点就出曲线。起点 ${pts[0].net_liq.toLocaleString(undefined, { maximumFractionDigits: 0 })} ${pts[0].currency}(${pts[0].snap_date})。`,
								`Day 1 · recorded daily at 09:07 SGT; the curve appears at two points. Start ${pts[0].net_liq.toLocaleString(undefined, { maximumFractionDigits: 0 })} ${pts[0].currency} (${pts[0].snap_date}).`
							)}
						</p>
					{/if}
				</div>
			{/each}
		{/if}
	</section>

	{#if trades.length === 0}
		<div
			class="rounded-lg border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground"
		>
			{tr(
				'暂无持仓 — 策略暖机中,通道填满后开始建仓。',
				'No positions yet — strategies are warming up; trades appear once the channel fills.'
			)}
		</div>
	{:else}
		<!-- Open positions -->
		<h2 class="mb-2 text-sm font-semibold text-foreground">
			{tr('当前持仓', 'Open')} ({open.length})
		</h2>
		<div class="mb-6 overflow-x-auto rounded-lg border border-border">
			<table class="w-full text-left text-xs">
				<thead class="bg-secondary/50 text-muted-foreground">
					<tr>
						<th class="px-3 py-2">{tr('标的', 'Instrument')}</th>
						<th class="px-3 py-2">{tr('策略', 'Strategy')}</th>
						<th class="px-3 py-2 text-right">{tr('数量', 'Qty')}</th>
						<th class="px-3 py-2 text-right">{tr('开仓价', 'Open')}</th>
						<th class="px-3 py-2 text-right">{tr('开仓时间', 'Opened')}</th>
					</tr>
				</thead>
				<tbody>
					{#each open as x, i (i)}
						<tr class="border-t border-border">
							<td class="px-3 py-2 font-mono text-foreground">{x.instrument}</td>
							<td class="px-3 py-2 text-muted-foreground">{x.strategy}</td>
							<td class="px-3 py-2 text-right font-mono">{x.quantity ?? '—'}</td>
							<td class="px-3 py-2 text-right font-mono"
								>{x.open_rate != null ? fmtUSD(x.open_rate) : '—'}</td
							>
							<td class="px-3 py-2 text-right text-muted-foreground">{fmtTime(x.open_date)}</td>
						</tr>
					{:else}
						<tr
							><td colspan="5" class="px-3 py-4 text-center text-muted-foreground"
								>{tr('无', 'none')}</td
							></tr
						>
					{/each}
				</tbody>
			</table>
		</div>

		<!-- Closed positions -->
		<h2 class="mb-2 text-sm font-semibold text-foreground">
			{tr('已平仓', 'Closed')} ({closed.length - nSuperseded}){#if nSuperseded}
				· {t(lang, 'nautilus.superseded')} ({nSuperseded}){/if}
		</h2>
		<div class="overflow-x-auto rounded-lg border border-border">
			<table class="w-full text-left text-xs">
				<thead class="bg-secondary/50 text-muted-foreground">
					<tr>
						<th class="px-3 py-2">{tr('标的', 'Instrument')}</th>
						<th class="px-3 py-2">{tr('策略', 'Strategy')}</th>
						<th class="px-3 py-2 text-right">{tr('开/平', 'Open/Close')}</th>
						<th class="px-3 py-2 text-right">{tr('盈亏', 'PnL')}</th>
						<th class="px-3 py-2 text-right">{tr('收益率', 'Return')}</th>
						<th class="px-3 py-2 text-right">{tr('平仓时间', 'Closed')}</th>
					</tr>
				</thead>
				<tbody>
					{#each closed as x, i (i)}
						{@const stale = isSuperseded(x)}
						<tr class="border-t border-border">
							<td class="px-3 py-2 font-mono text-foreground">{x.instrument}</td>
							<td class="px-3 py-2 text-muted-foreground">{x.strategy}</td>
							<td class="px-3 py-2 text-right font-mono whitespace-nowrap text-muted-foreground">
								{x.open_rate != null ? fmtUSD(x.open_rate) : '—'} → {!stale && x.close_rate != null
									? fmtUSD(x.close_rate)
									: '—'}
							</td>
							<td class="px-3 py-2 text-right font-mono {pnlClass(stale ? null : x.realized_pnl)}">
								{#if stale}
									<span
										class="rounded-full border border-border bg-muted px-2 py-0.5 font-sans text-[10px] whitespace-nowrap text-muted-foreground"
										title={t(lang, 'nautilus.supersededHint')}
										>{t(lang, 'nautilus.superseded')}</span
									>
								{:else}
									{x.realized_pnl != null ? fmtUSD(x.realized_pnl) : '—'}
								{/if}
							</td>
							<!-- profit_pct is stored as a FRACTION (Nautilus realized_return), not a percent -->
							<td class="px-3 py-2 text-right font-mono {pnlClass(stale ? null : x.profit_pct)}"
								>{!stale && x.profit_pct != null ? fmtPct(x.profit_pct * 100) : '—'}</td
							>
							<td class="px-3 py-2 text-right text-muted-foreground"
								>{!stale && x.close_date ? fmtTime(x.close_date) : '—'}</td
							>
						</tr>
					{:else}
						<tr
							><td colspan="6" class="px-3 py-4 text-center text-muted-foreground"
								>{tr('无', 'none')}</td
							></tr
						>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>
