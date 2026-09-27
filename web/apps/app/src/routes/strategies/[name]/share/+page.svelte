<script lang="ts">
	import type { PageData } from './$types';
	import { fmtPct, fmtTime } from '$lib/utils';

	let { data }: { data: PageData } = $props();

	const strategyName = $derived(data.strategyName);
	const topRuns = $derived(data.topRuns);
	const wfLatest = $derived(data.wfLatest);
	const trades = $derived(data.trades);
	const bestRun = $derived(data.bestRun);

	// KPI derivations
	const bestProfit = $derived(bestRun?.total_profit_pct ?? null);
	const bestSharpe = $derived(bestRun?.sharpe ?? null);
	const bestCalmar = $derived(bestRun?.calmar ?? null);
	const totalRuns = $derived(topRuns.length);

	// Equity curve SVG path from cumulative profit_abs
	const equityCurve = $derived(() => {
		if (!trades || trades.length === 0) return null;
		const closedTrades = trades.filter((t) => t.profit_abs != null);
		if (closedTrades.length === 0) return null;

		let cumulative = 0;
		const points: number[] = closedTrades.map((t) => {
			cumulative += t.profit_abs ?? 0;
			return cumulative;
		});

		const W = 800;
		const H = 160;
		const pad = 8;
		const minY = Math.min(0, ...points);
		const maxY = Math.max(0, ...points);
		const rangeY = maxY - minY || 1;

		const toX = (i: number) => pad + (i / Math.max(points.length - 1, 1)) * (W - pad * 2);
		const toY = (v: number) => H - pad - ((v - minY) / rangeY) * (H - pad * 2);
		const zeroY = toY(0);

		const pathD = points
			.map((v, i) => `${i === 0 ? 'M' : 'L'}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`)
			.join(' ');

		const finalPositive = points[points.length - 1] >= 0;

		return { pathD, zeroY, W, H, finalPositive };
	});

	function signClass(v: number | null | undefined): string {
		if (v == null) return 'text-gray-500';
		return v > 0 ? 'text-green-400' : v < 0 ? 'text-red-400' : 'text-gray-500';
	}

	function wfChipColor(p: number | null): string {
		if (p == null) return 'bg-gray-800 text-gray-400';
		if (p > 5) return 'bg-green-900 text-green-300 border border-green-700';
		if (p > 0) return 'bg-yellow-900 text-yellow-300 border border-yellow-700';
		return 'bg-red-900 text-red-300 border border-red-700';
	}
</script>

<svelte:head>
	<title>{strategyName} — Strategy Report | PandaQuant</title>
	<meta
		name="description"
		content="Backtest performance report for {strategyName} on PandaQuant."
	/>
</svelte:head>

<div class="min-h-screen bg-background text-foreground">
	<main class="mx-auto max-w-3xl px-4 py-12">
		<!-- Header -->
		<header class="mb-10 text-center">
			<div
				class="mb-3 inline-flex items-center gap-2 rounded-full border border-blue-800 bg-blue-950/40 px-3 py-1 text-xs text-blue-300"
			>
				Powered by PandaQuant
			</div>
			<h1 class="mt-2 text-4xl font-bold tracking-tight" style="color:#4a9eff">{strategyName}</h1>
			<p class="mt-2 text-sm text-gray-400">Strategy Performance Report</p>
		</header>

		<!-- KPI row -->
		<section class="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
			<div class="rounded-xl bg-gray-900 p-4 text-center">
				<div class="mb-1 text-[10px] tracking-widest text-gray-500 uppercase">Best Profit</div>
				<div class="text-2xl font-bold {signClass(bestProfit)}">{fmtPct(bestProfit)}</div>
			</div>
			<div class="rounded-xl bg-gray-900 p-4 text-center">
				<div class="mb-1 text-[10px] tracking-widest text-gray-500 uppercase">Best Sharpe</div>
				<div class="text-2xl font-bold {signClass(bestSharpe)}">
					{bestSharpe == null ? '—' : bestSharpe.toFixed(2)}
				</div>
			</div>
			<div class="rounded-xl bg-gray-900 p-4 text-center">
				<div class="mb-1 text-[10px] tracking-widest text-gray-500 uppercase">Best Calmar</div>
				<div class="text-2xl font-bold {signClass(bestCalmar)}">
					{bestCalmar == null ? '—' : bestCalmar.toFixed(2)}
				</div>
			</div>
			<div class="rounded-xl bg-gray-900 p-4 text-center">
				<div class="mb-1 text-[10px] tracking-widest text-gray-500 uppercase">Top Runs</div>
				<div class="text-2xl font-bold text-gray-200">{totalRuns}</div>
			</div>
		</section>

		<!-- Top 5 backtest table -->
		<section class="mb-8">
			<h2 class="mb-3 text-sm font-semibold text-gray-300">Top Backtest Runs</h2>
			<div class="overflow-x-auto rounded-xl border border-gray-800 bg-gray-900">
				<table class="w-full font-mono text-xs">
					<thead
						class="border-b border-gray-800 text-left text-[10px] tracking-wide text-gray-500 uppercase"
					>
						<tr>
							<th class="px-3 py-2.5">Run Date</th>
							<th class="px-3 py-2.5 text-right">Trades</th>
							<th class="px-3 py-2.5 text-right">Win%</th>
							<th class="px-3 py-2.5 text-right">Profit%</th>
							<th class="px-3 py-2.5 text-right">MaxDD%</th>
							<th class="px-3 py-2.5 text-right">Sharpe</th>
							<th class="px-3 py-2.5 text-right">Calmar</th>
						</tr>
					</thead>
					<tbody>
						{#each topRuns as r (r.id)}
							<tr class="border-t border-gray-800 transition-colors hover:bg-gray-800/60">
								<td class="px-3 py-2 text-gray-400">{fmtTime(r.imported_at)}</td>
								<td class="px-3 py-2 text-right text-gray-300">{r.total_trades ?? 0}</td>
								<td class="px-3 py-2 text-right text-gray-300">
									{r.win_rate_pct == null ? '—' : r.win_rate_pct.toFixed(1)}
								</td>
								<td class="px-3 py-2 text-right font-semibold {signClass(r.total_profit_pct)}">
									{fmtPct(r.total_profit_pct)}
								</td>
								<td
									class="px-3 py-2 text-right"
									class:text-red-400={(r.max_drawdown_pct ?? 0) > 20}
									class:text-gray-300={(r.max_drawdown_pct ?? 0) <= 20}
								>
									{r.max_drawdown_pct == null ? '—' : r.max_drawdown_pct.toFixed(1)}
								</td>
								<td class="px-3 py-2 text-right {signClass(r.sharpe)}">
									{r.sharpe == null ? '—' : r.sharpe.toFixed(2)}
								</td>
								<td class="px-3 py-2 text-right {signClass(r.calmar)}">
									{r.calmar == null ? '—' : r.calmar.toFixed(2)}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>

		<!-- Equity curve SVG -->
		{#if equityCurve()}
			{@const curve = equityCurve()!}
			<section class="mb-8">
				<h2 class="mb-3 text-sm font-semibold text-gray-300">Equity Curve (Best Run)</h2>
				<div class="rounded-xl border border-gray-800 bg-gray-900 p-4">
					<svg viewBox="0 0 {curve.W} {curve.H}" class="w-full" style="height:160px">
						<!-- Zero line -->
						<line
							x1="0"
							y1={curve.zeroY}
							x2={curve.W}
							y2={curve.zeroY}
							stroke="#374151"
							stroke-width="1"
							stroke-dasharray="4,4"
						/>
						<!-- Equity path -->
						<path
							d={curve.pathD}
							fill="none"
							stroke={curve.finalPositive ? '#22c55e' : '#ef4444'}
							stroke-width="2"
							stroke-linejoin="round"
							stroke-linecap="round"
						/>
					</svg>
					<p class="mt-2 text-center text-xs text-gray-500">
						Cumulative profit (USDT) — {trades.length} closed trades
					</p>
				</div>
			</section>
		{/if}

		<!-- WF heatmap -->
		{#if wfLatest.length > 0}
			<section class="mb-8">
				<h2 class="mb-3 text-sm font-semibold text-gray-300">Walk-Forward Results (Latest)</h2>
				<div class="flex flex-wrap gap-2">
					{#each wfLatest as w (w.id)}
						<div
							class="rounded-lg px-3 py-2 text-xs {wfChipColor(
								w.tot_profit_pct
							)} min-w-[80px] text-center"
						>
							<div class="mb-0.5 font-mono text-[10px] opacity-70">{w.window_label}</div>
							<div class="font-semibold">{fmtPct(w.tot_profit_pct)}</div>
						</div>
					{/each}
				</div>
				<p class="mt-3 text-xs text-gray-600">Green &gt;5% · Yellow &gt;0% · Red &lt;0%</p>
			</section>
		{/if}

		<!-- CTA -->
		<section class="mb-10 rounded-xl border border-blue-800 bg-blue-950/20 p-6 text-center">
			<p class="mb-3 text-sm text-gray-400">
				Want deeper analysis, live signals, and full trade history?
			</p>
			<a
				href="/strategies/{strategyName}"
				class="inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90"
				style="background-color:#4a9eff"
			>
				View Full Analysis →
			</a>
		</section>

		<!-- Footer -->
		<footer class="text-center text-xs text-gray-600">
			<span>Powered by </span>
			<a href="/" class="transition-colors hover:text-gray-400" style="color:#4a9eff">PandaQuant</a>
			<span class="mx-2">·</span>
			<span>Backtest results are not a guarantee of future performance.</span>
		</footer>
	</main>
</div>
