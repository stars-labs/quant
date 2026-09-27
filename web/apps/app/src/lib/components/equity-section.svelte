<script lang="ts">
	// US-equity section for the home page. The crypto leg dominated the dashboard; equity was
	// invisible (no live trades yet, backtests not surfaced). This gives equity a focused home:
	// honest live-paper status + a real HonestTrendEquity backtest leaderboard (numbers from
	// nautilus_equity/log_equity_backtests.py on the real IB catalog), plus jump-offs to the
	// semiconductor universe and walk-forward. No fabricated performance.
	import { page } from '$app/stores';
	import { type Lang } from '$lib/i18n';
	import type { NautilusBacktest, NautilusTrade } from '$lib/types';

	let {
		backtests = [],
		trades = []
	}: { backtests?: NautilusBacktest[]; trades?: NautilusTrade[] } = $props();

	const lang = $derived<Lang>($page.data.lang ?? 'zh');
	const en = $derived(lang === 'en');

	const openTrades = $derived(trades.filter((t) => !t.close_date));
	const closedTrades = $derived(
		trades.filter((t) => t.close_date).sort((a, b) => (a.close_date! < b.close_date! ? 1 : -1))
	);
	const top = $derived(backtests.slice(0, 6));
	const pct = (v: number | null | undefined) =>
		v === null || v === undefined ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`;
	const date = (s: string | null) => (s ? s.slice(0, 10) : '');
	const num = (v: number | null | undefined, d = 2) =>
		v === null || v === undefined ? '—' : v.toFixed(d);
</script>

<section class="mb-8 overflow-hidden rounded-2xl border bg-card">
	<div class="flex flex-wrap items-start justify-between gap-3 border-b border-border p-5 sm:p-6">
		<div class="min-w-0">
			<p class="text-xs font-medium tracking-wide text-primary uppercase">
				{en ? 'US Equity' : '美股量化'}
			</p>
			<h2 class="mt-1 text-xl font-bold tracking-tight">
				{en ? 'HonestTrend on NVDA · AMD · QQQ' : 'HonestTrend 趋势策略 · NVDA · AMD · QQQ'}
			</h2>
			<p class="mt-1.5 max-w-2xl text-sm text-muted-foreground">
				{en
					? 'EMA-trend strategy on real split-adjusted IB bars (2023–2026), running live on IB paper. A trend follower, not HFT — backtest and live are kept separate.'
					: 'EMA 趋势策略，跑在真实复权的 IB 行情上(2023–2026)，已在 IB 模拟盘实盘运行。是趋势跟随、不是高频 —— 回测与实盘分开看。'}
			</p>
		</div>
		<a
			href="/backtest"
			class="shrink-0 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
		>
			{en ? 'Backtest equities →' : '回测美股 →'}
		</a>
	</div>

	<!-- Live paper status — honest: usually no open position (trend signals are rare). -->
	<div class="border-b border-border p-5 sm:p-6">
		<div
			class="flex items-center gap-2 text-xs font-medium tracking-wide text-muted-foreground uppercase"
		>
			<span class="relative flex h-2 w-2">
				<span
					class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60"
				></span>
				<span class="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
			</span>
			{en ? 'Live · IB paper' : '实盘 · IB 模拟盘'}
		</div>
		{#if openTrades.length > 0}
			<div class="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
				{#each openTrades.slice(0, 6) as t, _i (_i)}
					<div class="rounded-md border border-border px-3 py-2 text-sm">
						<div class="flex items-center justify-between">
							<span class="font-medium">{t.instrument}</span>
							<span class="text-xs text-muted-foreground">{t.is_short ? 'short' : 'long'}</span>
						</div>
						<div class="mt-1 text-xs text-muted-foreground">
							{en ? 'entry' : '入场'}
							{num(t.open_rate)} · {t.strategy}
						</div>
					</div>
				{/each}
			</div>
		{:else if closedTrades.length > 0}
			<p class="mt-2 text-sm text-foreground">
				{en
					? 'Connected, currently flat. Most recent paper round-trips:'
					: '已连接，当前空仓。最近的模拟盘平仓记录：'}
			</p>
			<div class="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
				{#each closedTrades.slice(0, 6) as t, _i (_i)}
					<div class="rounded-md border border-border px-3 py-2 text-sm">
						<div class="flex items-center justify-between">
							<span class="font-medium">{t.instrument}</span>
							<span
								class="font-mono text-xs tabular-nums {(t.profit_pct ?? 0) >= 0
									? 'text-emerald-500'
									: 'text-red-500'}"
							>
								{pct(t.profit_pct)}
							</span>
						</div>
						<div class="mt-1 text-xs text-muted-foreground">
							{num(t.open_rate)} → {num(t.close_rate)} · {date(t.close_date)}
						</div>
					</div>
				{/each}
			</div>
		{:else}
			<p class="mt-2 text-sm text-foreground">
				{en
					? 'Connected, flat — no open position yet. The 1h EMA-50/100 trend signal hasn’t fired; the engine waits rather than forcing trades.'
					: '已连接，空仓 —— 暂无持仓。1 小时 EMA 50/100 趋势信号尚未触发；引擎宁可等待，也不硬凑交易。'}
			</p>
		{/if}
	</div>

	<!-- Backtest leaderboard — real numbers, sorted by return. -->
	<div class="p-5 sm:p-6">
		<div class="mb-3 flex items-baseline justify-between">
			<h3 class="text-sm font-semibold">
				{en ? 'Backtest leaderboard' : '回测排行'}
			</h3>
			<span class="text-xs text-muted-foreground">
				{en ? 'real IB bars · 2023–2026' : '真实 IB 行情 · 2023–2026'}
			</span>
		</div>
		{#if top.length === 0}
			<p class="text-sm text-muted-foreground">
				{en ? 'No equity backtests yet.' : '暂无美股回测。'}
			</p>
		{:else}
			<div class="overflow-x-auto">
				<table class="w-full text-sm">
					<thead>
						<tr class="border-b border-border text-left text-xs text-muted-foreground">
							<th class="py-2 pr-3 font-medium">{en ? 'Config' : '配置'}</th>
							<th class="px-3 py-2 text-right font-medium">{en ? 'Return' : '收益'}</th>
							<th class="px-3 py-2 text-right font-medium">{en ? 'Max DD' : '最大回撤'}</th>
							<th class="px-3 py-2 text-right font-medium">Sharpe</th>
							<th class="px-3 py-2 text-right font-medium">Calmar</th>
							<th class="py-2 pl-3 text-right font-medium">{en ? 'Trades' : '交易'}</th>
						</tr>
					</thead>
					<tbody>
						{#each top as b, _i (_i)}
							<tr class="border-b border-border/50 last:border-0">
								<td class="py-2 pr-3 font-medium">{b.label}</td>
								<td
									class="px-3 py-2 text-right font-mono tabular-nums {(b.total_profit_pct ?? 0) >= 0
										? 'text-emerald-500'
										: 'text-red-500'}"
								>
									{(b.total_profit_pct ?? 0) >= 0 ? '+' : ''}{num(b.total_profit_pct)}%
								</td>
								<td class="px-3 py-2 text-right font-mono text-muted-foreground tabular-nums">
									{num(b.max_drawdown_pct)}%
								</td>
								<td class="px-3 py-2 text-right font-mono tabular-nums">{num(b.sharpe)}</td>
								<td class="px-3 py-2 text-right font-mono tabular-nums">{num(b.calmar)}</td>
								<td class="py-2 pl-3 text-right font-mono text-muted-foreground tabular-nums">
									{b.total_trades ?? '—'}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="mt-3 text-xs text-muted-foreground">
				{en
					? 'Backtest ≠ live. Returns are over ~3 years on a small number of trend trades — high single-position drawdowns are real and shown, not hidden.'
					: '回测 ≠ 实盘。收益是约 3 年、少量趋势交易的结果 —— 单仓回撤偏大是真实的，照实显示，不藏。'}
			</p>
			<p class="mt-1 text-xs text-muted-foreground">
				{en
					? 'Few trades (1–7 over 3 years) is normal for trend following, but limits statistical significance.'
					: '趋势策略交易次数少(1–7 笔/3 年)属正常，但统计意义有限。'}
			</p>
		{/if}

		<div class="mt-4 flex flex-wrap gap-2 text-xs">
			<a
				href="/semis"
				class="rounded-md border border-border bg-secondary px-3 py-2 text-secondary-foreground hover:bg-accent"
			>
				{en ? '🔬 Semiconductor universe' : '🔬 半导体产业链'}
			</a>
			<a
				href="/wf"
				class="rounded-md border border-border bg-secondary px-3 py-2 text-secondary-foreground hover:bg-accent"
			>
				{en ? '📊 Walk-forward' : '📊 滚动前推回测'}
			</a>
			<a
				href="/nautilus"
				class="rounded-md border border-border bg-secondary px-3 py-2 text-secondary-foreground hover:bg-accent"
			>
				{en ? '⚡ Live execution' : '⚡ 实盘执行'}
			</a>
		</div>
	</div>
</section>
