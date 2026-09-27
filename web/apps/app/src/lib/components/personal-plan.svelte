<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { session } from '$lib/auth';
	import { loadPrefs, savePrefs, type UserPrefs } from '$lib/userPrefs';
	import {
		simulateDca,
		COIN_SYMBOLS,
		type CoinSymbol,
		type DcaPlan,
		type DcaResult,
		type OhlcByCoin
	} from '$lib/dcaSim';
	import { fmtUSD, fmtPct } from '$lib/utils';
	import { t, type Lang } from '$lib/i18n';

	async function loadPlotly() {
		if (typeof window === 'undefined') return null;
		if ((window as any).Plotly) return (window as any).Plotly;
		await new Promise<void>((res) => {
			const s = document.createElement('script');
			s.src = 'https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js';
			s.onload = () => res();
			document.head.appendChild(s);
		});
		return (window as any).Plotly;
	}

	let { ohlcByCoin }: { ohlcByCoin: OhlcByCoin } = $props();

	const lang = $derived<Lang>($page.data.lang ?? 'zh');

	let loaded = $state(false);
	let prefs = $state<UserPrefs | null>(null);
	let plan = $state<DcaPlan>({
		start_date: '2022-01-01',
		monthly_usdt: 500,
		mix: { BTC: 60, ETH: 20, BNB: 10, SOL: 10 }
	});
	let saveStatus = $state<'idle' | 'saving' | 'ok' | 'err'>('idle');
	let errMsg = $state('');
	let digest = $state(false);

	// Number() guard: dca_plan comes from the user_preferences jsonb row — a string
	// value would string-concat through the reduce and crash mixTotal.toFixed(0).
	const mixTotal = $derived(
		COIN_SYMBOLS.reduce((s, c) => s + Number(plan.mix?.[c] ?? 0), 0)
	);
	const mixValid = $derived(Math.abs(mixTotal - 100) < 0.5);

	const result = $derived<DcaResult | null>(
		$session && mixValid ? simulateDca(plan, ohlcByCoin) : null
	);

	let chartEl = $state<HTMLDivElement | null>(null);

	async function drawChart(r: DcaResult) {
		const Plotly = await loadPlotly();
		if (!Plotly || !chartEl) return;
		const dates = r.timeline.map((t) => t.date);
		const values = r.timeline.map((t) => t.value);
		const invested = r.timeline.map((t) => t.cum_invested);

		Plotly.newPlot(
			chartEl,
			[
				{
					x: dates,
					y: invested,
					type: 'scatter',
					mode: 'lines',
					name: t(lang, 'plan.result.invested'),
					line: { color: '#6b7280', width: 1.5 },
					fill: 'tozeroy',
					fillcolor: 'rgba(107,114,128,0.1)'
				},
				{
					x: dates,
					y: values,
					type: 'scatter',
					mode: 'lines',
					name: t(lang, 'plan.result.value'),
					line: { color: 'hsl(210 100% 66%)', width: 2 }
				}
			],
			{
				template: 'plotly_dark',
				plot_bgcolor: 'hsl(222 15% 5%)',
				paper_bgcolor: 'hsl(222 14% 8%)',
				font: { color: 'hsl(0 0% 95%)', family: 'Inter', size: 11 },
				margin: { t: 10, b: 35, l: 55, r: 10 },
				xaxis: { type: 'date', gridcolor: 'hsl(222 14% 15%)', showgrid: true },
				yaxis: { title: 'USDT', gridcolor: 'hsl(222 14% 15%)', showgrid: true },
				legend: { orientation: 'h', y: 1.08, x: 0 },
				hovermode: 'x unified'
			},
			{ responsive: true, displaylogo: false, displayModeBar: false }
		);
	}

	$effect(() => {
		if (result && result.summary.total_invested > 0 && chartEl) drawChart(result);
	});

	onMount(async () => {
		if (!$session) {
			loaded = true;
			return;
		}
		try {
			prefs = await loadPrefs(fetch);
			if (prefs?.dca_plan) plan = { ...plan, ...prefs.dca_plan };
			digest = prefs?.email_digest ?? false;
		} catch (e) {
			errMsg = (e as Error).message;
		} finally {
			loaded = true;
		}
	});

	async function save() {
		if (!$session) return;
		saveStatus = 'saving';
		errMsg = '';
		try {
			prefs = await savePrefs(
				{ dca_plan: plan, email_digest: digest },
				$session.user.sub!,
				fetch
			);
			saveStatus = 'ok';
			setTimeout(() => (saveStatus = 'idle'), 2000);
		} catch (e) {
			saveStatus = 'err';
			errMsg = (e as Error).message;
		}
	}

	function fmt(key: string, vars: Record<string, string>) {
		let s = t(lang, key);
		for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, v);
		return s;
	}

	function setMix(c: CoinSymbol, v: number) {
		const next = { ...(plan.mix ?? {}) };
		next[c] = Math.max(0, Math.min(100, Math.round(v)));
		plan = { ...plan, mix: next };
	}

	function normalizeTo100() {
		const s = mixTotal;
		if (s <= 0) return;
		const next: Partial<Record<CoinSymbol, number>> = {};
		for (const c of COIN_SYMBOLS) next[c] = Math.round(((plan.mix?.[c] ?? 0) / s) * 100);
		// Fix rounding drift so sum is exactly 100.
		const drift = 100 - COIN_SYMBOLS.reduce((t, c) => t + (next[c] ?? 0), 0);
		if (drift !== 0) next.BTC = (next.BTC ?? 0) + drift;
		plan = { ...plan, mix: next };
	}

	const coinColor: Record<CoinSymbol, string> = {
		BTC: 'bg-orange-950 text-orange-300 border-orange-800',
		ETH: 'bg-blue-950 text-blue-300 border-blue-800',
		BNB: 'bg-yellow-950 text-yellow-300 border-yellow-800',
		SOL: 'bg-purple-950 text-purple-300 border-purple-800'
	};
</script>

<section class="mb-8 rounded-xl border-2 border-primary/40 bg-gradient-to-br from-primary/5 to-transparent p-5">
	<h2 class="text-base font-semibold">{t(lang, 'plan.title')}</h2>

	{#if !$session}
		<p class="mt-2 text-sm text-muted-foreground">{t(lang, 'plan.subtitleAnon')}</p>
		<a
			href="/login"
			class="mt-4 inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
		>
			{t(lang, 'plan.loginCta')}
		</a>
	{:else if !loaded}
		<p class="mt-2 text-sm text-muted-foreground">{t(lang, 'plan.loading')}</p>
	{:else}
		<div class="mt-4 grid gap-4 lg:grid-cols-3">
			<label class="flex flex-col gap-1 text-xs text-muted-foreground lg:col-span-1">
				{t(lang, 'plan.start')}
				<input
					type="date"
					bind:value={plan.start_date}
					class="rounded-md border border-border bg-background px-3 py-2 font-mono text-sm text-foreground"
				/>
			</label>
			<label class="flex flex-col gap-1 text-xs text-muted-foreground lg:col-span-1">
				{t(lang, 'plan.monthly')}
				<input
					type="number"
					min="10"
					max="100000"
					step="10"
					bind:value={plan.monthly_usdt}
					class="rounded-md border border-border bg-background px-3 py-2 font-mono text-sm text-foreground"
				/>
			</label>
			<div class="flex items-end lg:col-span-1">
				<button
					type="button"
					onclick={save}
					disabled={saveStatus === 'saving' || !mixValid}
					class="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
				>
					{saveStatus === 'saving' ? '…' : saveStatus === 'ok' ? t(lang, 'plan.saved') : t(lang, 'plan.save')}
				</button>
			</div>
		</div>

		<div class="mt-4 rounded-lg border bg-card p-4">
			<div class="mb-2 flex items-baseline justify-between">
				<span class="text-xs font-semibold uppercase text-muted-foreground">
					{t(lang, 'plan.mix')}
				</span>
				<div class="flex items-center gap-3 text-xs">
					<span
						class="font-mono"
						class:text-red-500={!mixValid}
						class:text-muted-foreground={mixValid}
					>
						Σ {mixTotal.toFixed(0)}%
					</span>
					{#if !mixValid}
						<button
							type="button"
							onclick={normalizeTo100}
							class="rounded border border-border px-2 py-0.5 hover:bg-accent"
						>
							{t(lang, 'plan.normalize')}
						</button>
					{/if}
				</div>
			</div>
			<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
				{#each COIN_SYMBOLS as c}
					<div class="flex items-center gap-2">
						<span class="w-12 shrink-0 rounded border px-1.5 py-0.5 text-center font-mono text-[10px] {coinColor[c]}">{c}</span>
						<input
							type="range"
							min="0"
							max="100"
							step="5"
							value={plan.mix?.[c] ?? 0}
							oninput={(e) => setMix(c, (e.currentTarget as HTMLInputElement).valueAsNumber)}
							class="min-w-0 flex-1 accent-primary"
						/>
						<input
							type="number"
							min="0"
							max="100"
							step="1"
							value={plan.mix?.[c] ?? 0}
							oninput={(e) => setMix(c, (e.currentTarget as HTMLInputElement).valueAsNumber)}
							class="w-14 rounded-md border border-border bg-background px-2 py-1 text-right font-mono text-xs"
						/>
						<span class="w-4 text-xs text-muted-foreground">%</span>
					</div>
				{/each}
			</div>
			<p class="mt-2 text-[11px] text-muted-foreground">{t(lang, 'plan.mixHint')}</p>
		</div>

		{#if result && result.summary.total_invested > 0}
			<div class="mt-5 grid gap-3 text-center font-mono sm:grid-cols-3 lg:grid-cols-5">
				<div class="rounded-lg border bg-card p-3">
					<div class="text-[10px] uppercase text-muted-foreground">{t(lang, 'plan.result.invested')}</div>
					<div class="mt-1 text-lg font-semibold">{fmtUSD(result.summary.total_invested)}</div>
				</div>
				<div class="rounded-lg border bg-card p-3">
					<div class="text-[10px] uppercase text-muted-foreground">{t(lang, 'plan.result.value')}</div>
					<div class="mt-1 text-lg font-semibold">{fmtUSD(result.summary.current_value)}</div>
				</div>
				<div class="rounded-lg border bg-card p-3">
					<div class="text-[10px] uppercase text-muted-foreground">{t(lang, 'plan.result.roi')}</div>
					<div
						class="mt-1 text-lg font-semibold"
						class:text-green-500={result.summary.roi_pct > 0}
						class:text-red-500={result.summary.roi_pct < 0}
					>
						{fmtPct(result.summary.roi_pct)}
					</div>
				</div>
				<div class="rounded-lg border bg-card p-3">
					<div class="text-[10px] uppercase text-muted-foreground">{t(lang, 'plan.result.scheduled')}</div>
					<div class="mt-1 text-lg font-semibold">{result.summary.n_scheduled_buys}</div>
				</div>
				<div class="rounded-lg border bg-card p-3">
					<div class="text-[10px] uppercase text-muted-foreground">{t(lang, 'plan.result.coins')}</div>
					<div class="mt-1 text-xs font-mono leading-tight">
						{#each COIN_SYMBOLS as c}
							{#if (result.summary.current_holdings[c] ?? 0) > 0}
								<div>{c} {(result.summary.current_holdings[c] ?? 0).toFixed(c === 'BTC' ? 4 : 2)}</div>
							{/if}
						{/each}
					</div>
				</div>
			</div>
		{:else if !mixValid}
			<p class="mt-4 text-xs text-red-500">{fmt('plan.mixError', { total: mixTotal.toFixed(0) })}</p>
		{:else}
			<p class="mt-4 text-xs text-muted-foreground">{t(lang, 'plan.emptyResult')}</p>
		{/if}

		{#if result && result.summary.total_invested > 0}
			<div bind:this={chartEl} class="mt-5 h-72 rounded-lg border bg-card"></div>
		{/if}

		<label class="mt-5 flex items-center gap-2 border-t border-border pt-4 text-xs">
			<input type="checkbox" bind:checked={digest} onchange={save} class="h-4 w-4" />
			<span class="text-foreground">{t(lang, 'plan.digest')}</span>
			<span class="text-muted-foreground">{t(lang, 'plan.digestHint')}</span>
		</label>

		{#if errMsg}
			<div class="mt-3 text-xs text-red-500">{fmt('plan.error', { msg: errMsg })}</div>
		{/if}
	{/if}
</section>
