<script lang="ts">
	import { onMount } from 'svelte';
	import { vps } from '$lib/api';
	import { DEFAULT_PAIRS } from '$lib/config';
	import type { OhlcRow, BacktestRun, BacktestTrade } from '$lib/types';
	import { page } from '$app/stores';
	import { t, type Lang } from '$lib/i18n';
	import TvChart from '$lib/components/tv-chart.svelte';

	const lang = $derived<Lang>($page.data.lang ?? 'zh');

	let pair = $state('BTC/USDT');
	let range: '7d' | '30d' | '90d' | '1y' | '5y' | 'all' = $state('1y');
	let runs = $state<BacktestRun[]>([]);
	let runId = $state<number | null>(null);
	let rows = $state<OhlcRow[]>([]);
	let source = $state('');
	let loadMs = $state(0);
	let loading = $state(false);
	let trades = $state<BacktestTrade[]>([]);

	const RANGE = {
		'7d': () => [new Date(Date.now() - 7 * 86400e3), new Date()],
		'30d': () => [new Date(Date.now() - 30 * 86400e3), new Date()],
		'90d': () => [new Date(Date.now() - 90 * 86400e3), new Date()],
		'1y': () => [new Date(Date.now() - 365 * 86400e3), new Date()],
		'5y': () => [new Date(Date.now() - 5 * 365 * 86400e3), new Date()],
		all: () => [new Date('2017-08-17T00:00:00Z'), new Date()]
	} as const;

	async function refresh() {
		const [from, to] = RANGE[range]();
		loading = true;
		const t0 = performance.now();
		try {
			const result = await vps.ohlcAuto(fetch, pair, { from, to, maxPoints: 2000 });
			rows = result.rows;
			source = result.source;
		} catch (e) {
			// Authed API call failed (likely 401 — JWT expired or unsigned).
			// Fall back to the anon-accessible public_ohlc_1d view for major
			// pairs so the chart still renders something useful.
			const PUBLIC_PAIRS = new Set(['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT']);
			if (PUBLIC_PAIRS.has(pair)) {
				try {
					rows = await vps.publicOhlcDaily(fetch, pair, {
						from: from.toISOString().slice(0, 10),
						to: to.toISOString().slice(0, 10),
						limit: 2000
					});
					source = 'public_ohlc_1d (anon)';
				} catch (e2) {
					console.error(e2);
					rows = [];
					source = 'error';
				}
			} else {
				console.error(e);
				rows = [];
				source = 'error';
			}
		}
		loadMs = Math.round(performance.now() - t0);

		if (runId) {
			try {
				const all = await vps.backtestTrades(fetch, runId);
				trades = all.filter((t) => t.pair === pair);
			} catch {
				trades = [];
			}
		} else {
			trades = [];
		}
		loading = false;
	}

	onMount(async () => {
		try {
			runs = await vps.backtestRuns(fetch, { limit: 50 });
		} catch {
			// no runs → the run picker stays empty; the chart itself still loads
		}
		await refresh();
	});

	$effect(() => {
		void range;
		void pair;
		void runId;
		refresh();
	});
</script>

<svelte:head>
	<title>Chart · Crypto Quant</title>
</svelte:head>

<main class="mx-auto w-full max-w-[1600px] px-4 py-8 sm:px-6">
	<div class="mb-4 flex items-baseline justify-between">
		<div>
			<h1 class="text-2xl font-semibold tracking-tight">{t(lang, 'chart.title')}</h1>
			<p class="mt-1 text-sm text-muted-foreground">{t(lang, 'chart.subtitle')}</p>
		</div>
	</div>

	<div class="mb-3 flex flex-wrap items-center gap-2 rounded-lg border bg-card p-3">
		<label class="flex items-center gap-2 text-xs text-muted-foreground">
			{t(lang, 'common.pair')}
			<select
				bind:value={pair}
				class="rounded-md border border-border bg-background px-3 py-1 font-mono text-sm"
			>
				{#each DEFAULT_PAIRS as p, _i (_i)}
					<option value={p}>{p}</option>
				{/each}
			</select>
		</label>
		<span class="ml-2 text-xs text-muted-foreground">{t(lang, 'chart.range')}</span>
		{#each ['7d', '30d', '90d', '1y', '5y', 'all'] as r (r)}
			<button
				type="button"
				onclick={() => (range = r as typeof range)}
				class="rounded-md px-3 py-1 text-xs font-medium transition-colors"
				class:bg-primary={range === r}
				class:text-primary-foreground={range === r}
				class:bg-secondary={range !== r}
				class:text-muted-foreground={range !== r}
				class:hover:bg-accent={range !== r}
			>
				{r.toUpperCase()}
			</button>
		{/each}
		<label class="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
			{t(lang, 'chart.overlay')}
			<select
				bind:value={runId}
				class="min-w-[280px] rounded-md border border-border bg-background px-3 py-1 text-sm"
			>
				<option value={null}>{t(lang, 'common.none')}</option>
				{#each runs as r, _i (_i)}
					<option value={r.id}
						>#{r.id}
						{r.strategy} · {r.total_trades} t · {(r.total_profit_pct ?? 0).toFixed(1)}%</option
					>
				{/each}
			</select>
		</label>
	</div>

	<div
		class="mb-3 flex flex-wrap gap-x-6 gap-y-1 rounded-md border bg-card px-4 py-2 font-mono text-xs text-muted-foreground"
	>
		<span><span class="font-semibold text-foreground">{t(lang, 'common.pair')}:</span> {pair}</span>
		<span
			><span class="font-semibold text-foreground">{t(lang, 'common.source')}:</span> {source}</span
		>
		<span
			><span class="font-semibold text-foreground">{t(lang, 'common.rows')}:</span>
			{rows.length}</span
		>
		<span
			><span class="font-semibold text-foreground">{t(lang, 'common.load')}:</span>
			{loadMs} ms</span
		>
		{#if trades.length}
			<span
				><span class="font-semibold text-foreground">{t(lang, 'chart.pairTrades')}:</span>
				{trades.length}</span
			>
		{/if}
	</div>

	<div class="overflow-hidden rounded-lg border bg-card">
		{#if rows.length > 0}
			<TvChart {rows} {trades} height={560} />
		{:else if loading}
			<div class="flex h-[560px] items-center justify-center text-sm text-muted-foreground">
				{t(lang, 'common.loading') ?? 'Loading…'}
			</div>
		{:else if source === 'error'}
			<div class="flex h-[560px] flex-col items-center justify-center gap-3 px-6 text-center">
				<div class="bdv-eyebrow text-[var(--loss)]">Chart unavailable</div>
				<p class="max-w-md text-sm text-muted-foreground">
					{t(lang, 'chart.error') ??
						'Chart data could not be loaded — your session may have expired or this pair is not accessible without login.'}
				</p>
				<a
					href="/login?next=/chart"
					class="bdv-num text-[11px] tracking-[0.12em] text-[var(--dawn-500)] uppercase hover:text-[var(--dawn-300)]"
					>→ Log in</a
				>
			</div>
		{:else}
			<!-- Successful query but 0 rows — usually means the OHLC data
			     pipeline hasn't ingested this range yet. Suggest a wider range. -->
			<div class="flex h-[560px] flex-col items-center justify-center gap-3 px-6 text-center">
				<div class="bdv-eyebrow text-[var(--warn)]">No data for this range</div>
				<p class="max-w-md text-sm text-muted-foreground">
					{lang === 'en'
						? `No OHLC data for ${pair} in the selected ${range.toUpperCase()} window. The data pipeline may be a few hours behind — try a wider range like 1Y or ALL.`
						: `${pair} 在选定的 ${range.toUpperCase()} 窗口内没有 OHLC 数据。数据管线可能滞后若干小时 — 试试更大的范围（1Y / ALL）。`}
				</p>
				<div class="flex gap-2">
					<button
						type="button"
						onclick={() => (range = '1y')}
						class="bdv-num text-[11px] tracking-[0.12em] text-[var(--dawn-500)] uppercase hover:text-[var(--dawn-300)]"
						>→ 1Y</button
					>
					<button
						type="button"
						onclick={() => (range = 'all')}
						class="bdv-num text-[11px] tracking-[0.12em] text-[var(--dawn-500)] uppercase hover:text-[var(--dawn-300)]"
						>→ ALL</button
					>
				</div>
			</div>
		{/if}
	</div>

	{#if trades.length}
		{@const winners = trades.filter((t) => (t.profit_abs ?? 0) > 0).length}
		{@const pl = trades.reduce((a, t) => a + (t.profit_abs ?? 0), 0)}
		<div class="mt-4 grid gap-3 sm:grid-cols-3">
			<div class="rounded-lg border bg-card p-4">
				<div class="text-[11px] text-muted-foreground uppercase">{t(lang, 'chart.pairTrades')}</div>
				<div class="mt-1 font-mono text-2xl font-semibold">{trades.length}</div>
			</div>
			<div class="rounded-lg border bg-card p-4">
				<div class="text-[11px] text-muted-foreground uppercase">{t(lang, 'chart.winRate')}</div>
				<div class="mt-1 font-mono text-2xl font-semibold">
					{((winners / trades.length) * 100).toFixed(1)}%
				</div>
			</div>
			<div class="rounded-lg border bg-card p-4">
				<div class="text-[11px] text-muted-foreground uppercase">{t(lang, 'chart.pnl')}</div>
				<div
					class="mt-1 font-mono text-2xl font-semibold"
					class:text-green-500={pl > 0}
					class:text-red-500={pl < 0}
				>
					${pl.toFixed(0)}
				</div>
			</div>
		</div>
	{/if}
</main>
