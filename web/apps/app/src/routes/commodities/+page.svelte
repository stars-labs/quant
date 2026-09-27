<script lang="ts">
	import type { PageData } from './$types';
	import type { Lang } from '$lib/i18n';
	import type { CommodityRow } from './+page.server';

	let { data }: { data: PageData } = $props();
	const lang = $derived<Lang>((data as { lang?: Lang }).lang ?? 'zh');
	const tr = (zh: string, en: string) => (lang === 'zh' ? zh : en);

	const commodities = $derived<CommodityRow[]>(data.commodities ?? []);

	// Freshness = newest snapshot ts across the rows (they land within seconds).
	const updated = $derived.by(() => {
		let best = '';
		for (const c of commodities) if (c.ts > best) best = c.ts;
		return best ? new Date(best).toLocaleString() : '';
	});

	// % change over the last `back` daily closes (≈21 trading days = 1 month,
	// ≈252 = 1 year). null when the series is too short or the base is unusable.
	function chg(closes: [number, number][], back: number): number | null {
		const n = closes.length;
		if (n < back + 1) return null;
		const base = closes[n - 1 - back][1];
		const last = closes[n - 1][1];
		if (!base || !isFinite(base) || !isFinite(last)) return null;
		return (last / base - 1) * 100;
	}

	const fmtChg = (v: number | null) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`);
	const fmtPrice = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 2 });

	function chipCls(v: number | null): string {
		if (v == null) return 'bg-muted text-muted-foreground';
		return v >= 0 ? 'bg-emerald-500/10 text-emerald-500' : 'bg-red-500/10 text-red-500';
	}
	function tickCls(v: number | null): string {
		if (v == null) return 'text-muted-foreground';
		return v >= 0 ? 'text-emerald-500' : 'text-red-500';
	}

	// Compact SVG sparkline over the last ~120 daily closes — same polyline
	// pattern as the /nautilus NetLiq curve.
	const SPARK_N = 120;
	function spark(closes: [number, number][], w = 280, h = 56, pad = 4): string {
		const pts = closes.slice(-SPARK_N).map((c) => c[1]);
		if (pts.length < 2) return '';
		const lo = Math.min(...pts);
		const hi = Math.max(...pts);
		const span = hi - lo || 1;
		return pts
			.map((v, i) => {
				const x = pad + (i / (pts.length - 1)) * (w - pad * 2);
				const y = pad + (1 - (v - lo) / span) * (h - pad * 2);
				return `${x.toFixed(1)},${y.toFixed(1)}`;
			})
			.join(' ');
	}
	function sparkUp(closes: [number, number][]): boolean {
		const pts = closes.slice(-SPARK_N);
		return (pts[pts.length - 1]?.[1] ?? 0) >= (pts[0]?.[1] ?? 0);
	}
</script>

<svelte:head>
	<title>{tr('商品期货行情 · 黄金 原油 铜', 'Commodity futures · gold, oil, copper')}</title>
	<meta
		name="description"
		content={tr(
			'黄金、原油等 12 个期货连续合约 —— 和币、美股同一个引擎回测与订阅信号。数据每 30 分钟更新。',
			'Gold, oil and 10 more continuous futures — backtest and subscribe to signals on the same engine as crypto and US equities. Data refreshes every 30 minutes.'
		)}
	/>
</svelte:head>

<main class="mx-auto max-w-6xl px-4 py-8 sm:px-6">
	<h1 class="text-2xl font-bold tracking-tight">{tr('🥇 商品 / Commodities', '🥇 Commodities')}</h1>
	<p class="mt-2 max-w-3xl text-sm text-muted-foreground">
		{tr(
			'黄金、原油等 12 个期货连续合约 —— 和币、美股同一个引擎回测与订阅信号。数据每 30 分钟更新。',
			'Gold, oil and 10 more continuous futures — backtest and subscribe to signals on the same engine as crypto and US equities. Data refreshes every 30 minutes.'
		)}
	</p>

	{#if commodities.length === 0}
		<div
			class="mt-8 rounded-lg border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground"
		>
			{tr(
				'行情快照暂不可用，稍后再来。',
				'Snapshots are unavailable right now — check back shortly.'
			)}
		</div>
	{:else}
		<div class="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
			{#each commodities as c (c.asset)}
				{@const closes = c.payload.closes}
				{@const last = closes[closes.length - 1]?.[1]}
				{@const d1 = chg(closes, 1)}
				{@const d30 = chg(closes, 21)}
				{@const y1 = chg(closes, 252)}
				<div class="rounded-xl border border-border bg-card p-4">
					<div class="flex items-baseline justify-between gap-2">
						<div class="text-sm font-semibold text-foreground">
							{lang === 'zh' ? c.payload.zh : c.payload.en}
							<span class="font-mono text-xs font-normal text-muted-foreground">({c.asset})</span>
						</div>
						<div class="text-right">
							<span class="font-mono text-base font-semibold tabular-nums"
								>{last != null ? fmtPrice(last) : '—'}</span
							>
							<span class="ml-1 font-mono text-xs tabular-nums {tickCls(d1)}">{fmtChg(d1)}</span>
						</div>
					</div>
					<div class="mt-2 flex flex-wrap gap-1.5">
						<span class="rounded px-2 py-0.5 font-mono text-xs tabular-nums {chipCls(d30)}"
							>30d {fmtChg(d30)}</span
						>
						<span class="rounded px-2 py-0.5 font-mono text-xs tabular-nums {chipCls(y1)}"
							>1y {fmtChg(y1)}</span
						>
					</div>
					<svg viewBox="0 0 280 56" class="mt-3 h-[56px] w-full" aria-hidden="true">
						<polyline
							points={spark(closes)}
							fill="none"
							stroke={sparkUp(closes) ? 'rgb(74 222 128)' : 'rgb(248 113 113)'}
							stroke-width="1.5"
							stroke-linejoin="round"
							stroke-linecap="round"
						/>
					</svg>
					<div class="mt-3 flex items-center gap-4 text-xs">
						<a
							href="/backtest?strategy=honest_trend&asset={c.asset}"
							class="text-primary hover:underline">{tr('回测 →', 'Backtest →')}</a
						>
						<a href="/backtest#signals" class="text-primary hover:underline"
							>{tr('订阅信号 →', 'Subscribe →')}</a
						>
					</div>
				</div>
			{/each}
		</div>
		<p class="mt-6 text-xs text-muted-foreground">
			{tr(
				`数据更新于 ${updated} · 每 30 分钟自动采集 · 非投资建议`,
				`Data updated ${updated} · auto-collected every 30 minutes · not investment advice`
			)}
		</p>
	{/if}
</main>
