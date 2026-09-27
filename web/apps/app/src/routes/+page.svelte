<script lang="ts">
	import Kpi from '$lib/components/kpi.svelte';
	import FactorBadges from '$lib/components/factor-badges.svelte';
	import InfoTip from '$lib/components/info-tip.svelte';
	import GreetingBanner from '$lib/components/greeting-banner.svelte';
	import Hero from '$lib/components/hero.svelte';
	import EquitySection from '$lib/components/equity-section.svelte';
	import MarketPulse from '$lib/components/market-pulse.svelte';
	import TrustIntro from '$lib/components/trust-intro.svelte';
	import AffiliateCta from '$lib/components/affiliate-cta.svelte';
	import { fmtPct, fmtTime } from '$lib/utils';
	import { t, type Lang } from '$lib/i18n';
	import type { PageData } from './$types';
	import { onMount } from 'svelte';
	import ChartInfo from '$lib/components/chart-info.svelte';
	import StrategyInfo from '$lib/components/strategy-info.svelte';

	let { data }: { data: PageData } = $props();
	const s = data.summary;
	const lang = $derived<Lang>(data.lang ?? 'zh');

	let strategyFilter = $state<string | null>(null);
	let timeframeFilter = $state<string | null>(null);

	const filtered = $derived.by(() => {
		let rs = data.recent_runs;
		if (strategyFilter) rs = rs.filter((r) => r.strategy === strategyFilter);
		if (timeframeFilter) rs = rs.filter((r) => r.timeframe === timeframeFilter);
		return rs.slice(0, 25);
	});

	function fmt(key: string, vars: Record<string, string | number>) {
		let s = t(lang, key);
		for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
		return s;
	}

	// Strategy performance leaderboard — best recent run per strategy
	const stratLeaderboard = $derived.by(() => {
		if (data.recent_runs.length === 0) return null;
		const byStrat = new Map<string, (typeof data.recent_runs)[0]>();
		for (const r of data.recent_runs) {
			const cur = byStrat.get(r.strategy);
			if (!cur || (r.started_at ?? '') > (cur.started_at ?? '')) byStrat.set(r.strategy, r);
		}
		const entries = [...byStrat.values()]
			.filter((r) => r.total_profit_pct != null)
			.sort((a, b) => b.total_profit_pct! - a.total_profit_pct!);
		const top = entries.slice(0, 3);
		const bottom = entries.slice(-3).reverse();
		return { top, bottom, total: entries.length };
	});

	// Per-strategy profit sparkline (last 5 runs, sorted by date)
	// Timeframe distribution of recent runs
	// Top pairs across recent runs by frequency
	// Sharpe leaderboard: best Sharpe per strategy from recent runs
	// Composite quality ranking: normalize sharpe + profit - drawdown into a single score
	// Weekly run volume: last 12 weeks of backtest activity
	// Hall of fame: top 8 individual runs by Sharpe
	// Top Calmar runs: best risk-adjusted return (return / max drawdown)
	// Strategy consistency: % of runs with positive profit per strategy (min 5 runs)
	// Profit factor leaderboard: best profit_factor per strategy from all recent runs
	// Run profit histogram: distribution of total_profit_pct across all runs (10 equal buckets)
	// Avg max drawdown by timeframe: which timeframes carry least downside risk on average?
	// Avg win_rate_pct per timeframe (distinct from drawdownByTimeframe, bestRunByTimeframe, tfRunDist)
	// Top 10 recent runs by profit_factor (distinct from profitFactorLeaderboard strategy-level aggregates, topCalmarRuns, recentRunSortinoLeaderboard)
	// Market regime mini-widget (client-side)
	let regimeBtc = $state<number | null>(null);
	let regimeFng = $state<{ value: number; label: string } | null>(null);
	let regimeLoading = $state(false);

	function regimeSignal(fng: number): { label: string; color: string; desc: string } {
		if (fng <= 25)
			return {
				label: lang === 'en' ? 'BUY ZONE' : '抄底区',
				color: 'text-green-400',
				desc:
					lang === 'en'
						? 'Extreme fear — historically best DCA window'
						: '极度恐慌 — 历史上最佳 DCA 时机'
			};
		if (fng >= 75)
			return {
				label: lang === 'en' ? 'CAUTION' : '谨慎区',
				color: 'text-red-400',
				desc:
					lang === 'en'
						? 'Extreme greed — reduce exposure, tighten stops'
						: '极度贪婪 — 减仓，收紧止损'
			};
		if (fng >= 55)
			return {
				label: lang === 'en' ? 'GREED' : '贪婪',
				color: 'text-yellow-400',
				desc:
					lang === 'en'
						? 'Greed — trend-following strategies performing well'
						: '贪婪 — 趋势跟随表现良好'
			};
		return {
			label: lang === 'en' ? 'NEUTRAL' : '中性',
			color: 'text-muted-foreground',
			desc: lang === 'en' ? 'Neutral — all strategies on equal footing' : '中性 — 各策略均势'
		};
	}

	onMount(async () => {
		regimeLoading = true;
		try {
			const [btcRes, fngRes] = await Promise.allSettled([
				fetch('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT'),
				fetch('https://api.alternative.me/fng/?limit=1')
			]);
			if (btcRes.status === 'fulfilled' && btcRes.value.ok) {
				const d = await btcRes.value.json();
				regimeBtc = parseFloat(d.price);
			}
			if (fngRes.status === 'fulfilled' && fngRes.value.ok) {
				const d = await fngRes.value.json();
				const v = parseInt(d.data?.[0]?.value ?? '50');
				regimeFng = { value: v, label: d.data?.[0]?.value_classification ?? '' };
			}
		} catch {
			/* silently ignore */
		} finally {
			regimeLoading = false;
		}
	});

	// Avg profit per trade (total_profit_abs / total_trades) by strategy — efficiency metric
	// Median sharpe ratio per timeframe from recent runs
</script>

<svelte:head>
	<title>{t(lang, 'home.title')} · BearDawnVerse Quant</title>
	<meta
		name="description"
		content="BearDawnVerse Quant — 回测你自己的策略，看什么真的有效。免代码回测、实时信号、公开账本与诚实回撤。"
	/>
	<meta property="og:title" content="{t(lang, 'home.title')} · BearDawnVerse Quant" />
	<meta
		property="og:description"
		content="BearDawnVerse Quant — 回测你自己的策略，看什么真的有效。免代码回测、实时信号、公开账本与诚实回撤。"
	/>
</svelte:head>

<main class="mx-auto w-full max-w-[1600px] px-4 py-10 sm:px-6">
	<Hero />
	<GreetingBanner ohlcByCoin={data.ohlcByCoin} />

	<div class="mb-10">
		<div class="bdv-eyebrow mb-2 text-[var(--gold-500)]">BearDawnVerse · Quant</div>
		<!-- div, not h1: the Hero above already carries the page's single h1 -->
		<div class="bdv-display text-[44px] leading-[1.05] font-bold tracking-[-0.02em]">
			{t(lang, 'home.title')}
		</div>
		<p class="mt-3 max-w-2xl text-[14px] text-muted-foreground">{t(lang, 'home.subtitle')}</p>
	</div>

	<MarketPulse pulse={data.semi_pulse} />

	<EquitySection backtests={data.equity_backtests} trades={data.equity_trades} />

	<TrustIntro />
	<AffiliateCta variant="card" />

	<section class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
		<Kpi
			label={t(lang, 'home.kpi.apiStatus')}
			value={data.health.api ? t(lang, 'home.kpi.apiOnline') : t(lang, 'home.kpi.apiDown')}
			tone={data.health.api ? 'good' : 'bad'}
			sub={t(lang, 'home.kpi.apiSub')}
		/>
		<Kpi
			label={t(lang, 'home.kpi.totalRuns')}
			value={s.total_runs}
			sub={fmt('home.kpi.totalRunsSub', { n: s.distinct_strategies })}
		/>
		<Kpi
			label={t(lang, 'home.kpi.totalTrades')}
			value={s.total_trades.toLocaleString()}
			sub={t(lang, 'home.kpi.totalTradesSub')}
		/>
		<Kpi label={t(lang, 'home.kpi.dca')} value={s.dca_count} sub={t(lang, 'home.kpi.dcaSub')} />
	</section>

	<section class="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
		<!-- ChartInfo overlays the card corner (not inside Kpi) because the Kpi card is
			 overflow-hidden; ChartInfo's fixed-position popover escapes the clipping. -->
		<div class="relative">
			<Kpi
				label={t(lang, 'home.kpi.bestProfit')}
				value={fmtPct(s.best_profit_pct)}
				tone={(s.best_profit_pct ?? 0) > 0 ? 'good' : 'bad'}
				sub={t(lang, 'home.kpi.bestProfitSub')}
			/>
			<div class="absolute top-3 right-3">
				<ChartInfo metric="bestProfit" {lang} size="xs" />
			</div>
		</div>
		<Kpi
			label={t(lang, 'home.kpi.minMaxDd')}
			value={s.min_max_dd == null ? '—' : s.min_max_dd.toFixed(1) + '%'}
			tone={(s.min_max_dd ?? 100) < 20 ? 'good' : 'bad'}
			sub={t(lang, 'home.kpi.minMaxDdSub')}
		/>
		<Kpi
			label={t(lang, 'home.kpi.bestSharpe')}
			value={s.best_sharpe == null ? '—' : s.best_sharpe.toFixed(2)}
			tone={(s.best_sharpe ?? 0) > 1 ? 'good' : 'default'}
			sub={t(lang, 'home.kpi.bestSharpeSub')}
		/>
		<Kpi
			label={t(lang, 'home.kpi.strategyCount')}
			value={s.distinct_strategies}
			sub={t(lang, 'home.kpi.strategyCountSub')}
		/>
	</section>

	<section class="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
		<a
			href="/strategies"
			class="group rounded-xl border bg-card p-6 transition-colors hover:border-primary"
		>
			<div class="text-2xl">📚</div>
			<div class="mt-2 font-semibold">{t(lang, 'home.card.strategies.title')}</div>
			<p class="mt-1 text-sm text-muted-foreground">
				{fmt('home.card.strategies.desc', { n: s.distinct_strategies })}
			</p>
			<div class="mt-3 text-xs text-primary opacity-0 transition-opacity group-hover:opacity-100">
				{t(lang, 'common.enter')}
			</div>
		</a>
		<a
			href="/dca"
			class="group rounded-xl border bg-card p-6 transition-colors hover:border-primary"
		>
			<div class="text-2xl">💰</div>
			<div class="mt-2 font-semibold">{t(lang, 'home.card.dca.title')}</div>
			<p class="mt-1 text-sm text-muted-foreground">{t(lang, 'home.card.dca.desc')}</p>
			<div class="mt-3 text-xs text-primary opacity-0 transition-opacity group-hover:opacity-100">
				{t(lang, 'common.enter')}
			</div>
		</a>
		<a
			href="/chart"
			class="group rounded-xl border bg-card p-6 transition-colors hover:border-primary"
		>
			<div class="text-2xl">📉</div>
			<div class="mt-2 font-semibold">{t(lang, 'home.card.chart.title')}</div>
			<p class="mt-1 text-sm text-muted-foreground">{t(lang, 'home.card.chart.desc')}</p>
			<div class="mt-3 text-xs text-primary opacity-0 transition-opacity group-hover:opacity-100">
				{t(lang, 'common.enter')}
			</div>
		</a>
		<a
			href="/wf"
			class="group rounded-xl border bg-card p-6 transition-colors hover:border-primary"
		>
			<div class="text-2xl">🧭</div>
			<div class="mt-2 font-semibold">{t(lang, 'home.card.wf.title')}</div>
			<p class="mt-1 text-sm text-muted-foreground">{t(lang, 'home.card.wf.desc')}</p>
			<div class="mt-3 text-xs text-primary opacity-0 transition-opacity group-hover:opacity-100">
				{t(lang, 'common.enter')}
			</div>
		</a>
	</section>

	<!-- Market regime widget (hidden entirely when the upstream fetch fails) -->
	{#if regimeLoading || regimeFng}
		<section class="mt-6 rounded-xl border bg-card p-4">
			<div class="flex flex-wrap items-center justify-between gap-4">
				<h2 class="text-sm font-semibold">{lang === 'en' ? '🌡️ Market Regime' : '🌡️ 市场状态'}</h2>
				{#if regimeLoading}
					<span class="text-xs text-muted-foreground">{t(lang, 'common.loading')}</span>
				{:else if regimeFng}
					{@const sig = regimeSignal(regimeFng.value)}
					<div class="flex flex-wrap items-center gap-6">
						{#if regimeBtc}
							<div class="text-center">
								<div class="text-[10px] text-muted-foreground uppercase">BTC</div>
								<div class="font-mono text-sm font-semibold">
									${regimeBtc.toLocaleString('en-US', { maximumFractionDigits: 0 })}
								</div>
							</div>
						{/if}
						<div class="text-center">
							<div class="text-[10px] text-muted-foreground uppercase">
								{lang === 'en' ? 'Fear & Greed' : '恐贪指数'}
							</div>
							<div class="font-mono text-sm font-semibold">
								{regimeFng.value}
								<span class="text-xs text-muted-foreground">{regimeFng.label}</span>
							</div>
						</div>
						<!-- FnG gauge bar -->
						<div class="min-w-32 flex-1">
							<div
								class="relative h-3 overflow-hidden rounded-full"
								style="background: linear-gradient(to right, #ef4444, #f97316, #eab308, #22c55e)"
							>
								<div
									class="absolute top-0 h-full w-1 rounded-full bg-white shadow"
									style="left: calc({regimeFng.value}% - 2px)"
								></div>
							</div>
							<div class="mt-0.5 flex justify-between text-[9px] text-muted-foreground">
								<span>Fear</span><span>Greed</span>
							</div>
						</div>
						<div class="text-center">
							<div class="text-[10px] text-muted-foreground uppercase">
								{lang === 'en' ? 'Signal' : '信号'}
							</div>
							<div class="text-sm font-bold {sig.color}">{sig.label}</div>
						</div>
					</div>
					<p class="w-full text-xs text-muted-foreground">{sig.desc}</p>
				{/if}
			</div>
		</section>
	{/if}

	{#if !data.isAuthed}
		<section
			class="mt-10 rounded-xl border-2 border-dashed border-primary/40 bg-gradient-to-br from-primary/5 to-transparent p-8 text-center"
		>
			<h2 class="text-lg font-semibold">{t(lang, 'home.anonGate.title')}</h2>
			<p class="mt-2 text-sm text-muted-foreground">{t(lang, 'home.anonGate.body')}</p>
			<a
				href="/login?next=/"
				class="mt-4 inline-block rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
			>
				{t(lang, 'home.anonGate.cta')}
			</a>
		</section>
	{:else}
		{#if stratLeaderboard && stratLeaderboard.total >= 3}
			{@const lb = stratLeaderboard}
			<section class="mt-10">
				<div class="mb-3 flex items-baseline justify-between">
					<h2 class="text-lg font-semibold">
						Strategy Leaderboard <span class="ml-1 text-sm font-normal text-muted-foreground"
							>(most recent run · {lb.total} strategies)</span
						>
						<ChartInfo metric="leaderboard" {lang} />
					</h2>
					<a href="/strategies" class="text-xs text-primary hover:underline">All strategies</a>
				</div>
				<div class="grid gap-3 sm:grid-cols-2">
					<div>
						<p class="mb-2 text-[11px] font-semibold tracking-wider text-green-400 uppercase">
							Top Performers
						</p>
						<div class="space-y-1.5">
							{#each lb.top as r, i (i)}
								<!-- StrategyInfo (a <button>) sits next to but outside the <a>
								 so HTML stays valid (no nested interactive controls) and the
								 i-click doesn't accidentally fire the link navigation. -->
								<div
									class="flex items-center gap-2 rounded-lg border border-green-800/30 bg-green-950/15 px-3 py-2 text-xs transition hover:border-green-600/50"
								>
									<a
										href={`/strategies/${r.strategy}`}
										class="flex min-w-0 flex-1 items-center gap-2"
									>
										<span class="w-4 shrink-0 font-bold text-green-400">#{i + 1}</span>
										<span class="flex-1 truncate font-semibold text-foreground">{r.strategy}</span>
										<span class="shrink-0 font-mono font-semibold text-green-400"
											>+{r.total_profit_pct!.toFixed(1)}%</span
										>
										<span class="shrink-0 font-mono text-[10px] text-muted-foreground"
											>S {r.sharpe == null ? '—' : r.sharpe.toFixed(1)}</span
										>
									</a>
									<StrategyInfo strategy={r.strategy} {lang} size="xs" />
								</div>
							{/each}
						</div>
					</div>
					<div>
						<p class="mb-2 text-[11px] font-semibold tracking-wider text-red-400 uppercase">
							Underperformers
						</p>
						<div class="space-y-1.5">
							{#each lb.bottom as r, i (i)}
								<div
									class="flex items-center gap-2 rounded-lg border border-red-800/30 bg-red-950/15 px-3 py-2 text-xs transition hover:border-red-600/50"
								>
									<a
										href={`/strategies/${r.strategy}`}
										class="flex min-w-0 flex-1 items-center gap-2"
									>
										<span class="w-4 shrink-0 font-bold text-red-400"
											>#{lb.total - lb.bottom.length + i + 1}</span
										>
										<span class="flex-1 truncate font-semibold text-foreground">{r.strategy}</span>
										<span
											class="shrink-0 font-mono font-semibold {(r.total_profit_pct ?? 0) >= 0
												? 'text-green-400'
												: 'text-red-400'}"
											>{(r.total_profit_pct ?? 0) >= 0 ? '+' : ''}{r.total_profit_pct!.toFixed(
												1
											)}%</span
										>
										<span class="shrink-0 font-mono text-[10px] text-muted-foreground"
											>S {r.sharpe == null ? '—' : r.sharpe.toFixed(1)}</span
										>
									</a>
									<StrategyInfo strategy={r.strategy} {lang} size="xs" />
								</div>
							{/each}
						</div>
					</div>
				</div>
			</section>
		{/if}

		<section class="mt-10">
			<div class="mb-3 flex items-baseline justify-between">
				<h2 class="text-lg font-semibold">{t(lang, 'home.recent.title')}</h2>
				<a href="/archive" class="text-xs text-primary hover:underline"
					>{t(lang, 'common.viewAll')}</a
				>
			</div>

			<div class="mb-3 flex flex-wrap items-center gap-2 text-xs">
				<span class="text-muted-foreground">{t(lang, 'home.filter.strategy')}</span>
				<button
					type="button"
					onclick={() => (strategyFilter = null)}
					class="rounded-md border px-2 py-1 transition-colors hover:bg-accent"
					class:border-primary={strategyFilter === null}
					class:text-primary={strategyFilter === null}
				>
					{t(lang, 'common.all')}
				</button>
				{#each data.strategy_options as opt, _i (_i)}
					<button
						type="button"
						onclick={() => (strategyFilter = strategyFilter === opt ? null : opt)}
						class="rounded-md border px-2 py-1 font-mono transition-colors hover:bg-accent"
						class:border-primary={strategyFilter === opt}
						class:text-primary={strategyFilter === opt}
					>
						{opt}
					</button>
				{/each}
			</div>

			<div class="mb-4 flex flex-wrap items-center gap-2 text-xs">
				<span class="text-muted-foreground">{t(lang, 'home.filter.tf')}</span>
				<button
					type="button"
					onclick={() => (timeframeFilter = null)}
					class="rounded-md border px-2 py-1 transition-colors hover:bg-accent"
					class:border-primary={timeframeFilter === null}
					class:text-primary={timeframeFilter === null}
				>
					{t(lang, 'common.all')}
				</button>
				{#each data.timeframe_options as opt, _i (_i)}
					<button
						type="button"
						onclick={() => (timeframeFilter = timeframeFilter === opt ? null : opt)}
						class="rounded-md border px-2 py-1 font-mono transition-colors hover:bg-accent"
						class:border-primary={timeframeFilter === opt}
						class:text-primary={timeframeFilter === opt}
					>
						{opt}
					</button>
				{/each}
			</div>

			<div class="overflow-x-auto rounded-lg border bg-card">
				<table class="w-full text-sm">
					<thead class="bg-secondary text-left text-[11px] text-muted-foreground uppercase">
						<tr>
							<th class="px-3 py-2.5"
								><span class="inline-flex items-center"
									>{t(lang, 'home.table.started')}<InfoTip
										text={t(lang, 'metric.tip.started')}
									/></span
								></th
							>
							<th class="px-3">{t(lang, 'home.table.strategy')}</th>
							<th class="px-3"
								><span class="inline-flex items-center"
									>{t(lang, 'home.table.tf')}<InfoTip text={t(lang, 'metric.tip.tf')} /></span
								></th
							>
							<th class="px-3"
								><span class="inline-flex items-center"
									>{t(lang, 'home.table.factors')}<InfoTip
										text={t(lang, 'metric.tip.factors')}
									/></span
								></th
							>
							<th class="px-3 text-right"
								><span class="inline-flex items-center"
									>{t(lang, 'home.table.trades')}<InfoTip
										text={t(lang, 'metric.tip.trades')}
									/></span
								></th
							>
							<th class="px-3 text-right"
								><span class="inline-flex items-center"
									>{t(lang, 'home.table.winRate')}<InfoTip text={t(lang, 'metric.tip.wr')} /></span
								></th
							>
							<th class="px-3 text-right"
								><span class="inline-flex items-center"
									>{t(lang, 'home.table.profit')}<InfoTip
										text={t(lang, 'metric.tip.profit')}
									/></span
								></th
							>
							<th class="px-3 text-right"
								><span class="inline-flex items-center"
									>{t(lang, 'home.table.maxDd')}<InfoTip text={t(lang, 'metric.tip.maxDd')} /></span
								></th
							>
							<th class="px-3 text-right"
								><span class="inline-flex items-center"
									>{t(lang, 'home.table.calmar')}<InfoTip
										text={t(lang, 'metric.tip.calmar')}
										placement="top"
									/></span
								></th
							>
							<th class="px-3 text-right"
								><span class="inline-flex items-center"
									>{t(lang, 'home.table.sharpe')}<InfoTip
										text={t(lang, 'metric.tip.sharpe')}
										placement="top"
									/></span
								></th
							>
						</tr>
					</thead>
					<tbody class="font-mono text-xs">
						{#each filtered as r (r.id)}
							<tr class="border-t border-border hover:bg-accent/50">
								<td class="px-3 py-2 text-muted-foreground">{fmtTime(r.started_at)}</td>
								<td class="px-3 font-semibold">
									<a href={`/strategies/${r.strategy}`} class="text-primary hover:underline">
										{r.strategy}
									</a>
								</td>
								<td class="px-3">{r.timeframe ?? '-'}</td>
								<td class="px-3">
									<FactorBadges factors={r.factors} size="xs" />
								</td>
								<td class="px-3 text-right">{r.total_trades ?? 0}</td>
								<td class="px-3 text-right"
									>{r.win_rate_pct == null ? '—' : r.win_rate_pct.toFixed(1)}</td
								>
								<td
									class="px-3 text-right"
									class:text-green-500={(r.total_profit_pct ?? 0) > 0}
									class:text-red-500={(r.total_profit_pct ?? 0) < 0}
								>
									{fmtPct(r.total_profit_pct)}
								</td>
								<td class="px-3 text-right" class:text-red-500={(r.max_drawdown_pct ?? 0) > 20}>
									{(r.max_drawdown_pct ?? 0).toFixed(2)}%
								</td>
								<td class="px-3 text-right">{r.calmar == null ? '-' : r.calmar.toFixed(2)}</td>
								<td class="px-3 text-right">{r.sharpe == null ? '—' : r.sharpe.toFixed(2)}</td>
							</tr>
						{/each}
						{#if filtered.length === 0}
							<tr
								><td class="px-3 py-6 text-center text-muted-foreground" colspan="10"
									>{t(lang, 'home.filter.empty')}</td
								></tr
							>
						{/if}
					</tbody>
				</table>
			</div>
		</section>
	{/if}

	<footer class="mt-16 border-t border-border pt-6 text-center text-xs text-muted-foreground">
		{t(lang, 'home.footer')}
	</footer>
</main>
