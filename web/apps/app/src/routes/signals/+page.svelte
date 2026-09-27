<script lang="ts">
	import type { PageData } from './$types';
	import type { NewsItem } from '$lib/types';
	import { fmtTime, fmtPct } from '$lib/utils';
	import { t, type Lang } from '$lib/i18n';
	import ChartInfo from '$lib/components/chart-info.svelte';
	import StrategyInfo from '$lib/components/strategy-info.svelte';

	let { data }: { data: PageData } = $props();
	const lang = $derived<Lang>(data.lang ?? 'zh');

	let query = $state('');

	// Newest first; free-text search over strategy + timeframe.
	const runs = $derived.by(() => {
		const sorted = [...data.runs].sort((a, b) =>
			(a.started_at ?? a.imported_at) < (b.started_at ?? b.imported_at) ? 1 : -1
		);
		const q = query.trim().toLowerCase();
		if (!q) return sorted;
		return sorted.filter(
			(r) => r.strategy.toLowerCase().includes(q) || (r.timeframe ?? '').toLowerCase().includes(q)
		);
	});

	const isGated = $derived(data.runs.length === 0);

	// Strategy freshness: days since last import per strategy
	const stratFreshness = $derived.by(() => {
		const now = Date.now();
		const byStrat = new Map<
			string,
			{ lastImport: string; runCount: number; bestProfit: number | null }
		>();
		for (const r of data.runs) {
			const ts = r.imported_at ?? r.started_at ?? '';
			if (!ts) continue;
			if (!byStrat.has(r.strategy))
				byStrat.set(r.strategy, { lastImport: ts, runCount: 0, bestProfit: null });
			const s = byStrat.get(r.strategy)!;
			if (ts > s.lastImport) s.lastImport = ts;
			s.runCount++;
			if (r.total_profit_pct != null && (s.bestProfit == null || r.total_profit_pct > s.bestProfit))
				s.bestProfit = r.total_profit_pct;
		}
		return [...byStrat.entries()]
			.map(([strategy, v]) => ({
				strategy,
				...v,
				daysAgo: Math.floor((now - new Date(v.lastImport).getTime()) / 86400000)
			}))
			.sort((a, b) => a.daysAgo - b.daysAgo);
	});

	// --- 市场快讯 / Market wire (curated headlines, reposted verbatim) ---
	type NewsCat = 'all' | 'crypto' | 'macro' | 'equity' | 'global';
	const NEWS_CATS: { cat: NewsCat; zh: string; en: string }[] = [
		{ cat: 'all', zh: '全部', en: 'All' },
		{ cat: 'crypto', zh: '加密', en: 'Crypto' },
		{ cat: 'macro', zh: '宏观', en: 'Macro' },
		{ cat: 'equity', zh: '美股', en: 'Equity' },
		{ cat: 'global', zh: '全球', en: 'Global' }
	];
	// Official-source chips (central banks / regulators) get an amber tint.
	const OFFICIAL_SOURCES = new Set(['Fed', 'SEC', 'ECB', 'Bank of England']);

	let newsCat = $state<NewsCat>('all');
	let newsExpanded = $state(false);

	const newsFiltered = $derived(
		newsCat === 'all' ? data.news : data.news.filter((n: NewsItem) => n.category === newsCat)
	);
	const newsShown = $derived(newsFiltered.slice(0, newsExpanded ? 60 : 20));

	/** Relative time (X 分钟/小时前) for fresh items, plain date otherwise. */
	function newsAgo(iso: string): string {
		const t = new Date(iso).getTime();
		if (!Number.isFinite(t)) return iso?.slice(0, 10) ?? '';
		const mins = Math.floor((Date.now() - t) / 60_000);
		if (mins < 1) return lang === 'zh' ? '刚刚' : 'just now';
		if (mins < 60) return lang === 'zh' ? `${mins} 分钟前` : `${mins}m ago`;
		const hrs = Math.floor(mins / 60);
		if (hrs < 24) return lang === 'zh' ? `${hrs} 小时前` : `${hrs}h ago`;
		return iso.slice(0, 10);
	}

	const stats = $derived.by(() => {
		const profits = data.runs.map((r) => r.total_profit_pct).filter((v): v is number => v != null);
		const avgProfit = profits.length ? profits.reduce((a, b) => a + b, 0) / profits.length : null;
		const lastActivity = data.runs[0]?.started_at ?? data.runs[0]?.imported_at ?? null;
		return { avgProfit, lastActivity, totalRuns: data.runs.length };
	});
</script>

<svelte:head>
	<title>{t(lang, 'signals.title')} · Crypto Quant</title>
</svelte:head>

<main class="mx-auto w-full max-w-[1600px] px-4 py-8 sm:px-6">
	<!-- Page header -->
	<header class="mb-6">
		<h1 class="text-2xl font-semibold tracking-tight">{t(lang, 'signals.title')}</h1>
		<p class="mt-1 text-sm text-muted-foreground">{t(lang, 'signals.subtitle')}</p>
	</header>

	<!-- Stats bar -->
	{#if !isGated}
		<div class="mb-6 grid grid-cols-2 gap-3">
			<div class="rounded-lg border border-border bg-card px-4 py-3">
				<div class="text-[11px] text-muted-foreground uppercase">Backtests</div>
				<div class="mt-1 font-mono text-lg font-semibold">{stats.totalRuns}</div>
				{#if stats.avgProfit != null}
					<div class="mt-1 text-xs text-muted-foreground">
						avg <span
							class="font-mono font-semibold"
							class:text-green-400={stats.avgProfit > 0}
							class:text-red-400={stats.avgProfit < 0}
							>{stats.avgProfit >= 0 ? '+' : ''}{stats.avgProfit.toFixed(1)}%</span
						>
					</div>
				{/if}
			</div>
			<div class="rounded-lg border border-border bg-card px-4 py-3">
				<div class="text-[11px] text-muted-foreground uppercase">Last Activity</div>
				<div class="mt-1 font-mono text-xs text-foreground">
					{stats.lastActivity ? fmtTime(stats.lastActivity) : '—'}
				</div>
			</div>
		</div>
	{/if}

	<!-- 市场快讯 / Market wire — curated headlines, reposted verbatim. Renders nothing when empty/failed. -->
	{#if data.news.length > 0}
		<section class="mb-6 rounded-xl border border-border bg-card p-4">
			<div class="mb-3 flex flex-wrap items-center justify-between gap-2">
				<h2 class="text-sm font-semibold">
					📰 市场快讯 / Market wire
					<a
						href="/globe"
						class="ml-2 text-[11px] font-normal text-muted-foreground hover:text-primary hover:underline"
						>🌍 {lang === 'zh' ? '上球看' : 'On the globe'}</a
					>
				</h2>
				<div class="flex gap-2">
					{#each NEWS_CATS as c (c.cat)}
						<button
							type="button"
							onclick={() => (newsCat = c.cat)}
							class="rounded-full px-3 py-1 text-xs font-medium transition-colors"
							class:bg-primary={newsCat === c.cat}
							class:text-primary-foreground={newsCat === c.cat}
							class:bg-secondary={newsCat !== c.cat}
							class:text-muted-foreground={newsCat !== c.cat}
							class:border={newsCat !== c.cat}
							class:border-border={newsCat !== c.cat}
						>
							{lang === 'zh' ? c.zh : c.en}
						</button>
					{/each}
				</div>
			</div>
			<ul class="divide-y divide-border/60">
				{#each newsShown as n (n.link)}
					<li class="flex items-start gap-3 py-2 text-sm">
						<span
							class="w-16 shrink-0 pt-0.5 font-mono text-[10px] text-muted-foreground tabular-nums"
							title={n.published_at}>{newsAgo(n.published_at)}</span
						>
						<span
							class="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold {OFFICIAL_SOURCES.has(
								n.source
							)
								? 'border border-amber-900/50 bg-amber-950/50 text-amber-400/90'
								: 'bg-secondary text-muted-foreground'}">{n.source}</span
						>
						<a
							href={n.link}
							target="_blank"
							rel="noopener"
							class="min-w-0 leading-snug text-foreground/90 hover:text-primary hover:underline"
							>{n.title} <span class="text-[10px] text-muted-foreground">↗</span></a
						>
					</li>
				{/each}
			</ul>
			{#if !newsExpanded && newsFiltered.length > 20}
				<button
					type="button"
					onclick={() => (newsExpanded = true)}
					class="mt-2 w-full rounded-lg border border-border bg-secondary py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
				>
					{lang === 'zh' ? '更多' : 'More'} ({newsFiltered.length - 20})
				</button>
			{/if}
			<p class="mt-3 text-[10px] text-muted-foreground">
				{lang === 'zh'
					? '标题原文转载,来源可点击 —— 我们不改写、不解读。'
					: 'Headlines reposted verbatim, sources clickable — we do not rewrite or editorialize.'}
			</p>
		</section>
	{/if}

	<!-- Sticky search + filter bar -->
	<div class="sticky top-14 z-40 mb-6 rounded-xl border border-border bg-card px-4 py-3">
		<div class="flex flex-col gap-3 sm:flex-row sm:items-center">
			<!-- Search -->
			<div class="relative flex-1">
				<span
					class="pointer-events-none absolute inset-y-0 left-3 flex items-center text-muted-foreground"
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						class="h-4 w-4"
						fill="none"
						viewBox="0 0 24 24"
						stroke="currentColor"
						stroke-width="2"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z"
						/>
					</svg>
				</span>
				<input
					type="search"
					bind:value={query}
					placeholder={t(lang, 'signals.search')}
					class="w-full rounded-lg border border-border bg-background py-2 pr-3 pl-9 text-sm text-foreground outline-none focus:border-primary focus:ring-1 focus:ring-primary"
				/>
			</div>
		</div>
	</div>

	<!-- Anon gate -->
	{#if isGated}
		<div class="rounded-xl border border-border bg-card p-10 text-center">
			<p class="mb-1 text-base font-semibold">{t(lang, 'signals.gate.title')}</p>
			<p class="mb-4 text-sm text-muted-foreground">{t(lang, 'signals.gate.body')}</p>
			<a
				href="/login?next=/signals"
				class="inline-block rounded-lg bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
			>
				{t(lang, 'signals.gate.cta')}
			</a>
		</div>

		<!-- Empty state after filtering -->
	{:else if runs.length === 0}
		<div
			class="rounded-xl border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground"
		>
			{t(lang, 'signals.empty')}
		</div>

		<!-- Signal feed -->
	{:else}
		<ul class="space-y-3">
			{#each runs as r (r.id)}
				{@const profit = r.total_profit_pct ?? 0}
				<li class="rounded-xl border border-l-4 border-border border-l-green-500 bg-card px-4 py-3">
					<div class="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
						<span
							class="shrink-0 rounded-full bg-green-950/60 px-2 py-0.5 text-xs font-bold text-green-400"
							>BACKTEST</span
						>
						<span class="shrink-0 text-xs text-muted-foreground tabular-nums"
							>{fmtTime(r.started_at ?? r.imported_at)}</span
						>
						{#if r.timeframe}
							<span
								class="shrink-0 rounded bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
								>{r.timeframe}</span
							>
						{/if}
						<span class="shrink-0 font-semibold">{r.strategy}</span>
						<StrategyInfo strategy={r.strategy} {lang} size="xs" />
						<span
							class:text-green-400={profit > 0}
							class:text-red-400={profit < 0}
							class:text-muted-foreground={profit === 0}
							class="shrink-0 font-mono font-semibold">{fmtPct(profit)}</span
						>
						{#if r.calmar != null}
							<span class="shrink-0 text-xs text-muted-foreground"
								>Calmar <span class="font-mono text-foreground">{r.calmar.toFixed(2)}</span></span
							>
						{/if}
						{#if r.sharpe != null}
							<span class="shrink-0 text-xs text-muted-foreground"
								>Sharpe <span class="font-mono text-foreground">{r.sharpe.toFixed(2)}</span></span
							>
						{/if}
						{#if r.total_trades != null}
							<span class="shrink-0 text-xs text-muted-foreground"
								><span class="font-mono text-foreground">{r.total_trades}</span> trades</span
							>
						{/if}
						{#if r.max_drawdown_pct != null}
							<span class="shrink-0 text-xs text-muted-foreground"
								>MaxDD <span class="font-mono text-red-500">{r.max_drawdown_pct.toFixed(1)}%</span
								></span
							>
						{/if}
					</div>
				</li>
			{/each}
		</ul>
	{/if}

	<details class="mt-8 rounded-xl border border-border bg-card">
		<summary class="cursor-pointer p-4 text-sm font-semibold text-muted-foreground"
			>📊 高级分析(给量化爱好者)/ Advanced analytics</summary
		>
		<div class="space-y-8 p-4 pt-0">
			{#if stratFreshness.length > 0}
				<section class="rounded-lg border bg-card p-5">
					<div class="mb-3 flex items-baseline justify-between">
						<h2 class="text-sm font-semibold">
							Strategy Freshness <ChartInfo metric="leaderboard" {lang} />
						</h2>
						<span class="text-[11px] text-muted-foreground">Days since last backtest import</span>
					</div>
					<div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
						{#each stratFreshness as s, _i (_i)}
							{@const tone =
								s.daysAgo <= 7
									? 'border-green-700/50 bg-green-950/20'
									: s.daysAgo <= 30
										? 'border-yellow-700/50 bg-yellow-950/20'
										: 'border-red-700/40 bg-red-950/15'}
							{@const badge =
								s.daysAgo <= 7
									? 'bg-green-500/25 text-green-400'
									: s.daysAgo <= 30
										? 'bg-yellow-500/20 text-yellow-400'
										: 'bg-red-500/20 text-red-400'}
							<a
								href="/strategies/{s.strategy}"
								class="flex items-center justify-between rounded-lg border {tone} px-3 py-2 transition hover:opacity-80"
							>
								<div class="min-w-0">
									<div class="truncate text-xs font-semibold">{s.strategy}</div>
									<div class="font-mono text-[10px] text-muted-foreground">
										{s.runCount} runs · best {s.bestProfit != null
											? (s.bestProfit >= 0 ? '+' : '') + s.bestProfit.toFixed(1) + '%'
											: '—'}
									</div>
								</div>
								<span class="ml-2 shrink-0 rounded-full px-2 py-0.5 font-mono text-[11px] {badge}">
									{s.daysAgo === 0 ? 'today' : s.daysAgo + 'd'}
								</span>
							</a>
						{/each}
					</div>
				</section>
			{/if}
		</div>
	</details>
</main>
