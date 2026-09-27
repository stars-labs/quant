<script lang="ts">
	import type { PageData } from './$types';
	import type { AssetData } from '$lib/marketData';
	import { t, type Lang } from '$lib/i18n';
	import Sparkline from '$lib/components/sparkline.svelte';

	let { data }: { data: PageData } = $props();
	const lang = $derived<Lang>(data.lang ?? 'zh');

	// --- 市场压力指数 (explainable composite; see strategies/stress_index.py) ---
	const stress = $derived(data.stress);
	let stressOpen = $state(false);

	const STRESS_LABEL_EN: Record<string, string> = {
		平静: 'Calm',
		正常: 'Normal',
		紧张: 'Tense',
		高压: 'High stress'
	};
	const STRESS_COMP_NAME: Record<string, { zh: string; en: string }> = {
		fng: { zh: '恐惧贪婪指数', en: 'Fear & Greed' },
		vix: { zh: 'VIX 恐慌指数', en: 'VIX' },
		funding: { zh: 'BTC 资金费率', en: 'BTC funding' },
		breadth: { zh: '美股宽度', en: 'US breadth' }
	};

	function stressColor(score: number): string {
		if (score < 25) return 'var(--profit)';
		if (score < 50) return 'var(--dawn-500)';
		if (score < 75) return 'var(--warn)';
		return 'var(--loss)';
	}

	type TabSymbol = 'BTC' | 'ETH';
	let activeTab = $state<TabSymbol>('BTC');

	const asset = $derived<AssetData | null>(activeTab === 'BTC' ? data.btc : data.eth);

	// --- Signal helpers ---
	type Signal = 'pos' | 'neu' | 'neg';

	function ma4ySignal(m: number): Signal {
		if (m < 0.8) return 'pos';
		if (m <= 1.5) return 'neu';
		return 'neg';
	}

	function rsiSignal(r: number): Signal {
		if (r < 35) return 'pos';
		if (r <= 70) return 'neu';
		return 'neg';
	}

	function fngSignal(f: number): Signal {
		if (f < 25) return 'pos';
		if (f <= 75) return 'neu';
		return 'neg';
	}

	function fundingSignal(apr: number): Signal {
		if (apr < -5) return 'pos';
		if (apr <= 15) return 'neu';
		return 'neg';
	}

	function macdSignal(cross: AssetData['macd_cross']): Signal {
		if (cross === 'bullish') return 'pos';
		if (cross === 'bearish') return 'neg';
		return 'neu';
	}

	function ma5wSignal(dir: AssetData['ma5w_direction']): Signal {
		if (dir === 'up') return 'pos';
		if (dir === 'down') return 'neg';
		return 'neu';
	}

	function stochSignal(k: number): Signal {
		if (k < 20) return 'pos';
		if (k > 80) return 'neg';
		return 'neu';
	}

	function signalLabel(s: Signal, l: Lang): string {
		const map: Record<Signal, { zh: string; en: string }> = {
			pos: { zh: '多头', en: 'Bullish' },
			neu: { zh: '中性', en: 'Neutral' },
			neg: { zh: '空头', en: 'Bearish' }
		};
		return l === 'en' ? map[s].en : map[s].zh;
	}

	function signalBg(s: Signal): string {
		// Use semantic vars so chips retune across dark/light themes.
		if (s === 'pos')
			return 'bg-[color-mix(in_oklab,var(--profit)_12%,transparent)] border-l-[3px] border-[var(--profit)] text-[var(--profit)]';
		if (s === 'neg')
			return 'bg-[color-mix(in_oklab,var(--loss)_12%,transparent)] border-l-[3px] border-[var(--loss)] text-[var(--loss)]';
		return 'bg-[color-mix(in_oklab,var(--warn)_12%,transparent)] border-l-[3px] border-[var(--warn)] text-[var(--warn)]';
	}

	function sparklineColor(s: Signal): string {
		// SVG color attributes accept var() in modern browsers — keeps sparkline
		// readable in both dark and light themes.
		if (s === 'pos') return 'var(--profit)';
		if (s === 'neg') return 'var(--loss)';
		return 'var(--warn)';
	}

	function fmtPrice(n: number): string {
		if (n >= 1000) return '$' + n.toLocaleString('en-US', { maximumFractionDigits: 0 });
		return '$' + n.toFixed(2);
	}

	function fmtMultiple(n: number): string {
		return n.toFixed(2) + 'x';
	}

	function fmtPct(n: number): string {
		return n.toFixed(2) + '%';
	}

	function fmtBillion(n: number): string {
		if (n >= 1e9) return '$' + (n / 1e9).toFixed(2) + 'B';
		if (n >= 1e6) return '$' + (n / 1e6).toFixed(1) + 'M';
		return '$' + n.toFixed(0);
	}

	function ma5wLabel(dir: AssetData['ma5w_direction'], l: Lang): string {
		if (l === 'en') return dir;
		if (dir === 'up') return '上升';
		if (dir === 'down') return '下降';
		return '平稳';
	}

	function fmtSnapshotTime(iso: string): string {
		const d = new Date(iso);
		const hh = String(d.getUTCHours()).padStart(2, '0');
		const mm = String(d.getUTCMinutes()).padStart(2, '0');
		return `${hh}:${mm}`;
	}

	// Derived signals — recomputed whenever asset changes
	const signals = $derived(
		asset
			? {
					ma4y: ma4ySignal(asset.ma4y_multiple),
					ma5w: ma5wSignal(asset.ma5w_direction),
					macd: macdSignal(asset.macd_cross),
					rsi: rsiSignal(asset.rsi_weekly),
					stoch: stochSignal(asset.stochrsi_k),
					fng: fngSignal(asset.fng_value),
					funding: fundingSignal(asset.funding_rate_apr)
				}
			: null
	);
</script>

<svelte:head>
	<title>{t(lang, 'nav.market')} · Crypto Quant</title>
</svelte:head>

<main class="mx-auto w-full max-w-[1600px] px-4 py-8 sm:px-6">
	<div class="">
		<!-- Page header -->
		<div class="mb-6">
			<h1 class="text-2xl font-bold tracking-tight text-foreground">
				{t(lang, 'market.title')}
			</h1>
			<p class="mt-1 text-sm text-muted-foreground">{t(lang, 'market.subtitle')}</p>
			{#if asset?.snapshotTs}
				<p class="mt-1 text-xs text-muted-foreground">
					{lang === 'en'
						? `Data updated ${fmtSnapshotTime(asset.snapshotTs)} UTC · auto-collected every 30 min`
						: `数据更新于 ${fmtSnapshotTime(asset.snapshotTs)} UTC · 每 30 分钟自动采集`}
				</p>
			{/if}
		</div>

		<!-- 市场压力指数 — explainable composite, never a black box -->
		{#if stress}
			<div class="mb-6 rounded-xl border border-border bg-card px-6 py-4">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<div class="flex items-center gap-4">
						<div>
							<span class="text-xs font-semibold tracking-widest text-muted-foreground uppercase">
								{lang === 'en' ? 'Market stress index' : '市场压力指数'}
							</span>
							<div class="mt-1 flex items-baseline gap-2">
								<span class="text-3xl font-bold" style="color: {stressColor(stress.stress_score)}">
									{stress.stress_score.toFixed(0)}
								</span>
								<span
									class="text-sm font-semibold"
									style="color: {stressColor(stress.stress_score)}"
								>
									{lang === 'en' ? (STRESS_LABEL_EN[stress.label] ?? stress.label) : stress.label}
								</span>
							</div>
						</div>
						<div class="hidden h-2 w-40 overflow-hidden rounded-full bg-secondary sm:block">
							<div
								class="h-full rounded-full transition-all"
								style="width: {stress.stress_score}%; background: {stressColor(
									stress.stress_score
								)}"
							></div>
						</div>
					</div>
					<button
						type="button"
						class="text-xs text-muted-foreground underline decoration-dotted underline-offset-4 hover:text-foreground"
						onclick={() => (stressOpen = !stressOpen)}
					>
						{stressOpen
							? lang === 'en'
								? 'Hide how it’s computed'
								: '收起计算明细'
							: lang === 'en'
								? 'How is this computed?'
								: '这个数怎么算的？'}
					</button>
				</div>
				{#if stressOpen}
					<div class="mt-4 grid gap-2 sm:grid-cols-2">
						{#each Object.entries(stress.components) as [key, c] (key)}
							<div class="rounded-lg border border-border bg-secondary/40 px-3 py-2 text-xs">
								<div class="flex items-center justify-between">
									<span class="font-semibold text-foreground">
										{lang === 'en'
											? (STRESS_COMP_NAME[key]?.en ?? key)
											: (STRESS_COMP_NAME[key]?.zh ?? key)}
									</span>
									<span class="text-muted-foreground">
										{lang === 'en' ? 'raw' : '原始值'}
										{c.raw} →
										<span class="font-semibold" style="color: {stressColor(c.score)}"
											>{c.score.toFixed(0)}</span
										>
									</span>
								</div>
								<p class="mt-1 text-muted-foreground">{c.note}</p>
							</div>
						{/each}
					</div>
					<p class="mt-3 text-xs text-muted-foreground">
						{lang === 'en'
							? `Composite = plain mean of available sub-scores (0 = calm, 100 = high stress). Hourly. Updated ${fmtSnapshotTime(stress.ts)} UTC. Not investment advice.`
							: `综合分 = 各分项的简单平均（0=平静，100=高压），每小时更新，最近一次 ${fmtSnapshotTime(stress.ts)} UTC。仅为数据汇总，不构成投资建议。`}
					</p>
				{/if}
			</div>
		{/if}

		<!-- Asset tab switcher -->
		<div class="mb-8 flex gap-2">
			<button
				type="button"
				onclick={() => (activeTab = 'BTC')}
				class="rounded-full border px-5 py-2 text-sm font-semibold transition-all"
				class:text-foreground={activeTab !== 'BTC'}
				class:border-border={activeTab !== 'BTC'}
				class:bg-secondary={activeTab !== 'BTC'}
				class:text-primary-foreground={activeTab === 'BTC'}
				class:border-transparent={activeTab === 'BTC'}
				style={activeTab === 'BTC'
					? 'background: linear-gradient(120deg, var(--dawn-500), var(--violet-500)); box-shadow: 0 0 14px color-mix(in oklab, var(--dawn-500) 30%, transparent);'
					: ''}
			>
				&#8383; BTC
			</button>
			<button
				type="button"
				onclick={() => (activeTab = 'ETH')}
				class="rounded-full border px-5 py-2 text-sm font-semibold transition-all"
				class:text-foreground={activeTab !== 'ETH'}
				class:border-border={activeTab !== 'ETH'}
				class:bg-secondary={activeTab !== 'ETH'}
				class:text-primary-foreground={activeTab === 'ETH'}
				class:border-transparent={activeTab === 'ETH'}
				style={activeTab === 'ETH'
					? 'background: linear-gradient(120deg, var(--dawn-500), var(--violet-500)); box-shadow: 0 0 14px color-mix(in oklab, var(--dawn-500) 30%, transparent);'
					: ''}
			>
				&#926; ETH
			</button>
		</div>

		{#if !asset || !signals}
			<div
				class="rounded-xl border border-dashed border-border bg-card p-12 text-center text-muted-foreground"
			>
				{t(lang, 'market.error')}
			</div>
		{:else}
			<!-- Current Price Banner -->
			<div class="mb-6 rounded-xl border border-border bg-card px-6 py-4">
				<div class="flex items-center justify-between">
					<div>
						<span class="text-xs font-semibold tracking-widest text-muted-foreground uppercase">
							{activeTab}/USDT {t(lang, 'market.currentPrice')}
						</span>
						<div class="mt-1 text-3xl font-bold text-foreground">{fmtPrice(asset.price)}</div>
					</div>
					<div class="text-right">
						<span class="text-xs text-muted-foreground">{t(lang, 'market.dataSource')}</span>
						<div class="mt-1 text-xs text-muted-foreground">Binance · Alternative.me</div>
					</div>
				</div>
			</div>

			<!-- Core read: three plain-question cards -->
			<section class="mb-8">
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
					<!-- MA4Y -->
					<div class="rounded-xl border border-border bg-card p-4">
						<div class="mb-1 text-sm font-bold text-foreground">
							{lang === 'en' ? 'Is it expensive or cheap right now?' : '现在贵还是便宜?'}
						</div>
						<div
							class="mb-2 text-[10px] font-semibold tracking-widest text-muted-foreground uppercase"
						>
							{t(lang, 'market.card.ma4y.title')}
						</div>
						<div class="mb-2 text-[26px] leading-none font-bold text-foreground">
							{fmtMultiple(asset.ma4y_multiple)}
						</div>
						<div class="mb-3 h-12">
							<Sparkline
								values={asset.price_series}
								color={sparklineColor(signals.ma4y)}
								height={48}
							/>
						</div>
						<div
							class="mb-2 rounded border-l-2 border-border bg-secondary px-3 py-2 text-xs text-muted-foreground"
						>
							{t(lang, 'market.card.ma4y.desc')}
						</div>
						<div class="rounded px-3 py-1.5 text-xs font-semibold {signalBg(signals.ma4y)}">
							{t(lang, 'market.signal')}: {signalLabel(signals.ma4y, lang)}
						</div>
					</div>
					<!-- MA5W Direction -->
					<div class="rounded-xl border border-border bg-card p-4">
						<div class="mb-1 text-sm font-bold text-foreground">
							{lang === 'en' ? 'Is the trend up or down?' : '趋势向上还是向下?'}
						</div>
						<div
							class="mb-2 text-[10px] font-semibold tracking-widest text-muted-foreground uppercase"
						>
							{t(lang, 'market.card.ma5w.title')}
						</div>
						<div class="mb-2 text-[26px] leading-none font-bold text-foreground">
							{ma5wLabel(asset.ma5w_direction, lang)}
						</div>
						<div class="mb-3 h-12">
							<Sparkline
								values={asset.price_series}
								color={sparklineColor(signals.ma5w)}
								height={48}
							/>
						</div>
						<div
							class="mb-2 rounded border-l-2 border-border bg-secondary px-3 py-2 text-xs text-muted-foreground"
						>
							{t(lang, 'market.card.ma5w.desc')}
						</div>
						<div class="rounded px-3 py-1.5 text-xs font-semibold {signalBg(signals.ma5w)}">
							{t(lang, 'market.signal')}: {signalLabel(signals.ma5w, lang)}
						</div>
					</div>

					<!-- Fear & Greed -->
					<div class="rounded-xl border border-border bg-card p-4">
						<div class="mb-1 text-sm font-bold text-foreground">
							{lang === 'en' ? 'How is market sentiment?' : '市场情绪如何?'}
						</div>
						<div
							class="mb-2 text-[10px] font-semibold tracking-widest text-muted-foreground uppercase"
						>
							{t(lang, 'market.card.fng.title')}
						</div>
						<div class="mb-1 text-[26px] leading-none font-bold text-foreground">
							{asset.fng_value}
						</div>
						<div class="mb-2 text-xs text-muted-foreground">{asset.fng_class}</div>
						<div class="mb-3 h-12">
							<Sparkline
								values={asset.fng_series}
								color={sparklineColor(signals.fng)}
								height={48}
							/>
						</div>
						<div
							class="mb-2 rounded border-l-2 border-border bg-secondary px-3 py-2 text-xs text-muted-foreground"
						>
							{t(lang, 'market.card.fng.desc')}
						</div>
						<div class="rounded px-3 py-1.5 text-xs font-semibold {signalBg(signals.fng)}">
							{t(lang, 'market.signal')}: {signalLabel(signals.fng, lang)}
						</div>
					</div>
				</div>
			</section>

			<!-- Advanced analytics: expert cards collapsed by default -->
			<details class="mt-8 rounded-xl border border-border bg-card">
				<summary class="cursor-pointer p-4 text-sm font-semibold text-muted-foreground"
					>📊 高级分析(给量化爱好者)/ Advanced analytics</summary
				>
				<div class="space-y-8 p-4 pt-0">
					<!-- Technicals -->
					<section>
						<h2
							class="mb-4 pl-3 text-base font-bold text-foreground"
							style="border-left: 4px solid var(--violet-500);"
						>
							{t(lang, 'market.section.technicals')}
						</h2>
						<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
							<!-- MACD -->
							<div class="rounded-xl border border-border bg-card p-4">
								<div
									class="mb-2 text-[10px] font-semibold tracking-widest text-muted-foreground uppercase"
								>
									{t(lang, 'market.card.macd.title')}
								</div>
								<div class="mb-2 text-[26px] leading-none font-bold text-foreground">
									{asset.macd_hist.toFixed(1)}
								</div>
								<div class="mb-3 h-12">
									<Sparkline
										values={asset.macd_hist_series}
										color={sparklineColor(signals.macd)}
										height={48}
									/>
								</div>
								<div
									class="mb-2 rounded border-l-2 border-border bg-secondary px-3 py-2 text-xs text-muted-foreground"
								>
									{t(lang, 'market.card.macd.desc')}
								</div>
								<div class="rounded px-3 py-1.5 text-xs font-semibold {signalBg(signals.macd)}">
									{t(lang, 'market.signal')}: {signalLabel(signals.macd, lang)}
								</div>
							</div>

							<!-- RSI -->
							<div class="rounded-xl border border-border bg-card p-4">
								<div
									class="mb-2 text-[10px] font-semibold tracking-widest text-muted-foreground uppercase"
								>
									{t(lang, 'market.card.rsi.title')}
								</div>
								<div class="mb-2 text-[26px] leading-none font-bold text-foreground">
									{asset.rsi_weekly.toFixed(1)}
								</div>
								<div class="mb-3 h-12">
									<Sparkline
										values={asset.rsi_series}
										color={sparklineColor(signals.rsi)}
										height={48}
									/>
								</div>
								<div
									class="mb-2 rounded border-l-2 border-border bg-secondary px-3 py-2 text-xs text-muted-foreground"
								>
									{t(lang, 'market.card.rsi.desc')}
								</div>
								<div class="rounded px-3 py-1.5 text-xs font-semibold {signalBg(signals.rsi)}">
									{t(lang, 'market.signal')}: {signalLabel(signals.rsi, lang)}
								</div>
							</div>

							<!-- StochRSI -->
							<div class="rounded-xl border border-border bg-card p-4">
								<div
									class="mb-2 text-[10px] font-semibold tracking-widest text-muted-foreground uppercase"
								>
									{t(lang, 'market.card.stochrsi.title')}
								</div>
								<div class="mb-2 text-[26px] leading-none font-bold text-foreground">
									K {asset.stochrsi_k.toFixed(1)}
								</div>
								<div class="mb-3 h-12">
									<Sparkline
										values={asset.rsi_series}
										color={sparklineColor(signals.stoch)}
										height={48}
									/>
								</div>
								<div
									class="mb-2 rounded border-l-2 border-border bg-secondary px-3 py-2 text-xs text-muted-foreground"
								>
									{t(lang, 'market.card.stochrsi.desc')}
								</div>
								<div class="rounded px-3 py-1.5 text-xs font-semibold {signalBg(signals.stoch)}">
									{t(lang, 'market.signal')}: {signalLabel(signals.stoch, lang)}
								</div>
							</div>
						</div>
					</section>

					<!-- Sentiment: funding -->
					<section>
						<h2
							class="mb-4 pl-3 text-base font-bold text-foreground"
							style="border-left: 4px solid var(--violet-500);"
						>
							{t(lang, 'market.section.sentiment')}
						</h2>
						<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
							<!-- Funding Rate APR -->
							<div class="rounded-xl border border-border bg-card p-4">
								<div
									class="mb-2 text-[10px] font-semibold tracking-widest text-muted-foreground uppercase"
								>
									{t(lang, 'market.card.funding.title')}
								</div>
								<div class="mb-2 text-[26px] leading-none font-bold text-foreground">
									{fmtPct(asset.funding_rate_apr)}
								</div>
								<div class="mb-3 h-12">
									<Sparkline
										values={asset.oi_series}
										color={sparklineColor(signals.funding)}
										height={48}
									/>
								</div>
								<div
									class="mb-2 rounded border-l-2 border-border bg-secondary px-3 py-2 text-xs text-muted-foreground"
								>
									{t(lang, 'market.card.funding.desc')}
								</div>
								<div class="rounded px-3 py-1.5 text-xs font-semibold {signalBg(signals.funding)}">
									{t(lang, 'market.signal')}: {signalLabel(signals.funding, lang)}
								</div>
							</div>
						</div>
					</section>

					<!-- Leverage: open interest -->
					<section>
						<h2
							class="mb-4 pl-3 text-base font-bold text-foreground"
							style="border-left: 4px solid var(--violet-500);"
						>
							{t(lang, 'market.section.leverage')}
						</h2>
						<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
							<div class="rounded-xl border border-border bg-card p-4">
								<div
									class="mb-2 text-[10px] font-semibold tracking-widest text-muted-foreground uppercase"
								>
									{t(lang, 'market.card.oi.title')}
								</div>
								<div class="mb-2 text-[26px] leading-none font-bold text-foreground">
									{fmtBillion(asset.open_interest_usd)}
								</div>
								<div class="mb-3 h-12">
									<Sparkline values={asset.oi_series} color="#7b5fff" height={48} />
								</div>
								<div
									class="mb-2 rounded border-l-2 border-border bg-secondary px-3 py-2 text-xs text-muted-foreground"
								>
									{t(lang, 'market.card.oi.desc')}
								</div>
								<div
									class="rounded border-l-[3px] border-[var(--violet-500)] bg-[color-mix(in_oklab,var(--violet-500)_10%,transparent)] px-3 py-1.5 text-xs font-semibold text-[var(--violet-500)]"
								>
									{t(lang, 'market.signal')}: {t(lang, 'market.signal.info')}
								</div>
							</div>
						</div>
					</section>

					<!-- Derivatives sentiment: L/S, taker, top traders -->
					<section>
						<h2
							class="mb-4 pl-3 text-base font-bold text-foreground"
							style="border-left: 4px solid var(--violet-500);"
						>
							{t(lang, 'market.derivatives.title')}
						</h2>

						{#if asset}
							{@const longPct = asset.ls_ratio / (1 + asset.ls_ratio)}
							{@const shortPct = 1 - longPct}
							{@const lsColor =
								asset.ls_ratio > 1.05 ? '#18a058' : asset.ls_ratio < 0.95 ? '#e84040' : '#888'}
							{@const takerColor =
								asset.taker_ratio > 1.05
									? '#18a058'
									: asset.taker_ratio < 0.95
										? '#e84040'
										: '#888'}
							{@const topTraderColor =
								asset.top_trader_ls > 1.05
									? '#18a058'
									: asset.top_trader_ls < 0.95
										? '#e84040'
										: '#888'}
							{@const composite = (asset.ls_ratio + asset.taker_ratio + asset.top_trader_ls) / 3}

							<div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
								<!-- Card 1: Long/Short Ratio -->
								<div class="rounded-xl border border-border bg-card p-4">
									<div
										class="mb-2 text-[10px] font-semibold tracking-widest text-muted-foreground uppercase"
									>
										{t(lang, 'market.ls.title')}
									</div>
									<div class="mb-1 text-[26px] leading-none font-bold" style="color: {lsColor};">
										{asset.ls_ratio.toFixed(3)}
									</div>
									<div class="mb-3 text-xs text-muted-foreground">
										{lang === 'en' ? 'longs' : '多'}
										{(longPct * 100).toFixed(1)}% / {lang === 'en' ? 'shorts' : '空'}
										{(shortPct * 100).toFixed(1)}%
									</div>
									<!-- Long/Short split bar -->
									<div
										class="mb-3 h-2 w-full overflow-hidden rounded-full"
										style="background: #e84040;"
									>
										<div
											class="h-full rounded-full"
											style="width: {(longPct * 100).toFixed(1)}%; background: #18a058;"
										></div>
									</div>
									<!-- Sparkline -->
									<svg width="80" height="28" viewBox="0 0 80 28" class="overflow-visible">
										{#if asset.ls_ratio_series.length > 1}
											{@const pts = asset.ls_ratio_series}
											{@const step = 80 / (pts.length - 1)}
											<polyline
												points={pts.map((v, i) => `${i * step},${28 - v * 26}`).join(' ')}
												fill="none"
												stroke={lsColor}
												stroke-width="1.5"
												stroke-linejoin="round"
												stroke-linecap="round"
											/>
										{/if}
									</svg>
								</div>

								<!-- Card 2: Taker Buy/Sell Ratio -->
								<div class="rounded-xl border border-border bg-card p-4">
									<div
										class="mb-2 text-[10px] font-semibold tracking-widest text-muted-foreground uppercase"
									>
										{t(lang, 'market.taker.title')}
									</div>
									<div class="mb-1 text-[26px] leading-none font-bold" style="color: {takerColor};">
										{asset.taker_ratio.toFixed(3)}
									</div>
									<div class="mb-3 text-xs text-muted-foreground">
										{#if asset.taker_ratio > 1.05}
											{lang === 'en' ? 'Buy dominant' : '买方主动'}
										{:else if asset.taker_ratio < 0.95}
											{lang === 'en' ? 'Sell dominant' : '卖方主动'}
										{:else}
											{lang === 'en' ? 'Balanced' : '均衡'}
										{/if}
									</div>
									<!-- Sparkline -->
									<svg width="80" height="28" viewBox="0 0 80 28" class="overflow-visible">
										{#if asset.taker_ratio_series.length > 1}
											{@const pts = asset.taker_ratio_series}
											{@const step = 80 / (pts.length - 1)}
											<polyline
												points={pts.map((v, i) => `${i * step},${28 - v * 26}`).join(' ')}
												fill="none"
												stroke={takerColor}
												stroke-width="1.5"
												stroke-linejoin="round"
												stroke-linecap="round"
											/>
										{/if}
									</svg>
								</div>

								<!-- Card 3: Top Trader L/S -->
								<div class="rounded-xl border border-border bg-card p-4">
									<div
										class="mb-2 text-[10px] font-semibold tracking-widest text-muted-foreground uppercase"
									>
										{t(lang, 'market.toptrader.title')}
									</div>
									<div
										class="mb-1 text-[26px] leading-none font-bold"
										style="color: {topTraderColor};"
									>
										{asset.top_trader_ls.toFixed(3)}
									</div>
									<div class="mb-2 text-xs text-muted-foreground">
										{lang === 'en' ? 'Elite positioning' : '大户持仓方向'}
									</div>
									{#if Math.abs(asset.top_trader_ls - asset.ls_ratio) > 0.2}
										<div
											class="mb-2 rounded bg-[color-mix(in_oklab,var(--warn)_10%,transparent)] px-2 py-1 text-xs font-semibold text-[var(--warn)]"
										>
											{lang === 'en' ? '⚠ Divergence: retail vs elite' : '⚠ 散户 vs 大户方向背离'}
										</div>
									{/if}
								</div>
							</div>

							<!-- Interpretation bar -->
							<div class="mt-4 rounded-xl border border-border bg-card px-5 py-3">
								{#if composite > 1.1}
									<p class="text-sm font-semibold text-[var(--loss)]">
										{lang === 'en'
											? '⚠ Market over-leveraged long — correction risk elevated'
											: '⚠ 市场过度多头，留意回调风险'}
									</p>
								{:else if composite < 0.9}
									<p class="text-sm font-semibold text-[var(--profit)]">
										{lang === 'en'
											? '↑ Short-heavy market — potential reversal zone'
											: '↑ 空头主导，可能触底信号'}
									</p>
								{:else}
									<p class="text-sm text-muted-foreground">
										{lang === 'en'
											? 'Market positioning balanced — no strong directional bias detected'
											: '市场多空持仓均衡，暂无明显方向偏差'}
									</p>
								{/if}
								<p class="mt-1 text-xs text-muted-foreground">
									{lang === 'en' ? 'Composite signal (avg of 3 ratios):' : '综合信号（三项均值）:'}
									{composite.toFixed(3)}
								</p>
							</div>
						{/if}
					</section>
				</div>
			</details>

			<!-- Footer note -->
			<p class="text-center text-xs text-muted-foreground">
				{t(lang, 'market.footer')}
			</p>
		{/if}
	</div>
</main>
