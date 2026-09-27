<script lang="ts">
	import type { PageData } from './$types';
	import Kpi from '$lib/components/kpi.svelte';
	import PersonalPlan from '$lib/components/personal-plan.svelte';
	import DcaLedger from '$lib/components/dca-ledger.svelte';
	import BinanceConnect from '$lib/components/binance-connect.svelte';
	import { fmtTime, fmtUSD } from '$lib/utils';
	import { t, type Lang } from '$lib/i18n';
	import { onMount } from 'svelte';
	import AlertSubscribe from '$lib/components/alert-subscribe.svelte';

	let { data }: { data: PageData } = $props();
	const lang = $derived<Lang>(data.lang ?? 'zh');

	const cumMax = $derived(Math.max(1, ...data.cumulative.map((c) => c.cum)));

	const REPORT_CARDS = $derived([
		{
			title: t(lang, 'dca.report.weekly.title'),
			desc: t(lang, 'dca.report.weekly.desc'),
			href: '/reports/dca_backtest/index.html'
		},
		{
			title: t(lang, 'dca.report.dist.title'),
			desc: t(lang, 'dca.report.dist.desc'),
			href: '/reports/dca_backtest/multiplier_distribution.html'
		},
		{
			title: t(lang, 'dca.report.comparison.title'),
			desc: t(lang, 'dca.report.comparison.desc'),
			href: '/reports/dca_backtest/dca_comparison.html'
		}
	]);

	// Cumulative DCA SVG area chart
	const cumChart = $derived.by(() => {
		const pts = data.cumulative;
		if (pts.length < 2) return null;
		const W = 560, H = 100, PAD = 4;
		const maxVal = Math.max(1, ...pts.map(p => p.cum));
		const toX = (i: number) => PAD + (i / (pts.length - 1)) * (W - PAD * 2);
		const toY = (v: number) => H - PAD - ((v / maxVal) * (H - PAD * 2));
		const linePts = pts.map((p, i) => `${toX(i).toFixed(1)},${toY(p.cum).toFixed(1)}`).join(' ');
		const areaPts = `${PAD},${H - PAD} ` + linePts + ` ${W - PAD},${H - PAD}`;
		const last = pts[pts.length - 1];
		return { linePts, areaPts, W, H, PAD, last, maxVal };
	});

	// DCA projection chart
	let projMonthly = $state(500);
	let projBtcPrice = $state<number | null>(null);
	const SCENARIOS = $derived([
		{ label: lang === 'en' ? 'Bear (0% CAGR)' : '熊市 (0%)', cagr: 0,   color: 'var(--ch-loss-strong)' },
		{ label: lang === 'en' ? 'Base (40% CAGR)' : '基础 (40%)', cagr: 0.4, color: 'var(--ch-warn)' },
		{ label: lang === 'en' ? 'Extreme bull (100% CAGR, unlikely to repeat)' : '极端牛市 (100%,历史不可重复)', cagr: 1.0, color: 'var(--ch-profit-strong)' },
	] as const);
	const projectionData = $derived.by(() => {
		const btc = projBtcPrice ?? 60000;
		const months = 60; // 5 years
		const W = 560, H = 140;
		const curves = SCENARIOS.map(sc => {
			let btcStack = 0;
			const pts: [number, number][] = [[0, 0]];
			for (let m = 1; m <= months; m++) {
				const btcBought = projMonthly / btc;
				btcStack += btcBought;
				const btcFuturePrice = btc * Math.pow(1 + sc.cagr, m / 12);
				pts.push([m, btcStack * btcFuturePrice]);
			}
			return { ...sc, pts, final: btcStack * btc * Math.pow(1 + sc.cagr, 5) };
		});
		const maxVal = Math.max(...curves.flatMap(c => c.pts.map(p => p[1])), 1);
		function toX(m: number) { return (m / months) * W; }
		function toY(v: number) { return H - (v / maxVal) * H; }
		return curves.map(c => ({
			...c,
			polyline: c.pts.map(([m, v]) => `${toX(m).toFixed(1)},${toY(v).toFixed(1)}`).join(' '),
		}));
	});
	onMount(async () => {
		try {
			const r = await fetch('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT');
			if (r.ok) { const d = await r.json(); projBtcPrice = parseFloat(d.price); }
		} catch { /* ignore */ }
	});

</script>

<svelte:head>
	<title>{t(lang, 'dca.title')}</title>
	<meta name="description" content="Smart DCA：基于恐贪指数的智能定投，每一笔触发、金额与时间全部公开可查。" />
	<meta property="og:title" content={t(lang, 'dca.title')} />
	<meta property="og:description" content="Smart DCA：基于恐贪指数的智能定投，每一笔触发、金额与时间全部公开可查。" />
</svelte:head>

<main class="w-full max-w-[1600px] mx-auto px-4 sm:px-6 py-8">
	<header class="mb-8">
		<h1 class="text-3xl font-semibold tracking-tight">{t(lang, 'dca.title')}</h1>
		<p class="mt-2 max-w-3xl text-sm text-muted-foreground">{t(lang, 'dca.subtitle')}</p>
	</header>

	<!-- Telegram alert subscription — the component handles anonymous visitors itself. -->
	<div class="mb-8">
		<AlertSubscribe />
	</div>

	<PersonalPlan ohlcByCoin={data.ohlcByCoin} />
	<DcaLedger />
	<BinanceConnect />

	<section class="mb-8 grid gap-3 sm:grid-cols-2">
		<Kpi label={t(lang, 'dca.kpi.scheduled')} value={data.summary.scheduled_count} sub={t(lang, 'dca.kpi.scheduledSub')} />
		<Kpi label={t(lang, 'dca.kpi.scheduledUsdt')} value={fmtUSD(data.summary.scheduled_total_usdt)} sub="USDT" />
	</section>

	<section class="mb-8">
		<div class="rounded-lg border bg-card p-5">
			<h2 class="mb-1 text-sm font-semibold">{lang === 'en' ? 'How much has been invested in total?' : '一共投了多少钱?'}</h2>
			<p class="mb-3 text-[10px] text-muted-foreground">{lang === 'en' ? 'Cumulative deployment curve' : '累积投入曲线'}</p>
			{#if data.cumulative.length === 0}
				<div class="rounded border border-dashed p-6 text-center text-xs text-muted-foreground">
					{t(lang, 'dca.cumEmpty')}
				</div>
			{:else}
				{#if cumChart}
					<div class="mb-3 overflow-x-auto">
						<svg viewBox="0 0 {cumChart.W} {cumChart.H}" class="w-full" style="height:100px;min-width:280px">
							<defs>
								<linearGradient id="cumGrad" x1="0" y1="0" x2="0" y2="1">
									<stop offset="0%" stop-color="var(--ch-violet-light)" />
									<stop offset="100%" stop-color="var(--ch-violet-light)" />
								</linearGradient>
							</defs>
							<polygon points={cumChart.areaPts} fill="url(#cumGrad)" />
							<polyline points={cumChart.linePts} fill="none" stroke="rgba(129,140,248,0.9)" stroke-width="2" stroke-linejoin="round" />
						</svg>
					</div>
					<div class="flex items-center justify-between font-mono text-xs text-muted-foreground">
						<span>{fmtTime(data.cumulative[0].ts)}</span>
						<span class="text-indigo-400 font-semibold">Σ {fmtUSD(cumChart.last.cum)}</span>
						<span>{fmtTime(cumChart.last.ts)}</span>
					</div>
				{/if}
				<div class="mt-3 max-h-48 overflow-y-auto space-y-1 font-mono text-xs">
					{#each data.cumulative.slice(-15) as c}
						<div class="flex items-center gap-2">
							<span class="w-32 shrink-0 text-muted-foreground">{fmtTime(c.ts)}</span>
							<div class="relative flex-1 h-3 rounded bg-muted/30">
								<div
									class="absolute left-0 top-0 h-full rounded bg-indigo-500/50"
									style="width: {(c.cum / cumMax) * 100}%"
								></div>
							</div>
							<span class="w-20 shrink-0 text-right text-foreground">{fmtUSD(c.amount)}</span>
							<span class="w-24 shrink-0 text-right text-muted-foreground">Σ {fmtUSD(c.cum)}</span>
						</div>
					{/each}
				</div>
			{/if}
		</div>

	</section>

	{#if data.log.length > 0}
		<section class="mb-8">
			<h2 class="mb-3 text-sm font-semibold">{t(lang, 'dca.log.title')}</h2>
			<div class="overflow-hidden rounded-lg border bg-card">
				<table class="w-full text-xs">
					<thead class="bg-secondary text-left text-[10px] uppercase text-muted-foreground">
						<tr>
							<th class="px-3 py-2">{t(lang, 'common.time')}</th>
							<th class="px-3">{t(lang, 'dca.table.mode')}</th>
							<th class="px-3 text-right">{t(lang, 'dca.log.base')}</th>
							<th class="px-3 text-right">{t(lang, 'dca.log.mult')}</th>
							<th class="px-3 text-right">{t(lang, 'dca.log.actual')}</th>
							<th class="px-3 text-right">{t(lang, 'dca.table.fng')}</th>
							<th class="px-3">{t(lang, 'dca.log.cycle')}</th>
						</tr>
					</thead>
					<tbody class="font-mono">
						{#each data.log.slice(0, 30) as r}
							<tr class="border-t border-border hover:bg-accent/40">
								<td class="px-3 py-1.5 text-muted-foreground">{fmtTime(r.timestamp)}</td>
								<td class="px-3">{r.mode}</td>
								<td class="px-3 text-right">{fmtUSD(r.base_usdt)}</td>
								<td class="px-3 text-right">×{(r.multiplier ?? 1).toFixed(2)}</td>
								<td class="px-3 text-right text-foreground">{fmtUSD(r.amount_usdt)}</td>
								<td class="px-3 text-right">{r.fng_value ?? '—'}</td>
								<td class="px-3 text-muted-foreground">{r.cycle_signal ?? '—'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{/if}

	<!-- DCA projection chart -->
	<section class="mb-8 rounded-lg border bg-card p-5">
		<div class="mb-4 flex flex-wrap items-baseline justify-between gap-3">
			<h2 class="text-sm font-semibold">{lang === 'en' ? '📈 5-Year Accumulation Projection' : '📈 5年积累预测'}</h2>
			<div class="flex items-center gap-3 text-xs">
				<label class="flex items-center gap-2 text-muted-foreground">
					{lang === 'en' ? 'Monthly' : '月投'}
					<input type="number" bind:value={projMonthly} min="50" max="10000" step="50"
						class="w-20 rounded border border-border bg-background px-2 py-1 font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-primary" />
					USDT
				</label>
			</div>
		</div>
		<div class="overflow-x-auto">
			<svg viewBox="0 0 560 140" class="w-full" style="height:120px;min-width:280px">
				{#each [0.25, 0.5, 0.75, 1] as f}
					<line x1="0" y1={140*(1-f)} x2="560" y2={140*(1-f)} stroke="var(--ch-rule-faint)" stroke-width="1"/>
				{/each}
				{#each [12,24,36,48,60] as m}
					<line x1={m/60*560} y1="0" x2={m/60*560} y2="140" stroke="var(--ch-rule-faint)" stroke-width="1"/>
					<text x={m/60*560} y="138" text-anchor="middle" font-size="8" fill="var(--ch-rule-strong)">Y{m/12}</text>
				{/each}
				{#each projectionData as sc}
					<polyline points={sc.polyline} fill="none" stroke={sc.color} stroke-width="2"/>
				{/each}
			</svg>
		</div>
		<div class="mt-3 flex flex-wrap gap-4">
			{#each projectionData as sc}
				<div class="flex items-center gap-2 text-xs">
					<span class="inline-block h-0.5 w-6 rounded" style="background:{sc.color}"></span>
					<span class="text-muted-foreground">{sc.label}</span>
					<span class="font-mono font-semibold" style="color:{sc.color}">${sc.final.toLocaleString('en-US', { maximumFractionDigits: 0 })}</span>
				</div>
			{/each}
		</div>
		<p class="mt-2 text-[10px] text-muted-foreground">{lang === 'en' ? `BTC entry price: $${(projBtcPrice ?? 60000).toLocaleString('en-US', { maximumFractionDigits: 0 })} · assumes constant monthly DCA + CAGR applied to total BTC stack` : `BTC 入场价: $${(projBtcPrice ?? 60000).toLocaleString('en-US', { maximumFractionDigits: 0 })} · 假设固定月投 + 对全部 BTC 持仓应用 CAGR`}</p>
	</section>

	<section class="mb-8">
		<h2 class="mb-3 text-sm font-semibold">{t(lang, 'dca.reports')}</h2>
		<div class="grid gap-3 md:grid-cols-2">
			{#each REPORT_CARDS as c}
				<a
					href={c.href}
					data-sveltekit-reload
					class="group rounded-lg border bg-card p-4 transition-colors hover:border-primary"
				>
					<div class="font-semibold">{c.title}</div>
					<div class="mt-1 text-xs text-muted-foreground">{c.desc}</div>
					<div class="mt-2 font-mono text-[10px] text-primary opacity-0 transition-opacity group-hover:opacity-100">
						{c.href} →
					</div>
				</a>
			{/each}
		</div>
	</section>
</main>
