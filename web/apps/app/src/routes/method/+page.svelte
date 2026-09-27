<script lang="ts">
	// 方法论 — how every public signal is made, what it costs, where the data comes from, how the
	// coins were picked, what we tested and REJECTED, and a dated changelog. Static page: the
	// radar thresholds come from $lib/scan and the coin list from $lib/growth, so they cannot
	// drift from what /scan and the Telegram pushes use; the research numbers are copied from
	// STRATEGY_LEADERBOARD.md (2026-09-27 sections).
	import type { PageData } from './$types';
	import { resolve } from '$app/paths';
	import type { Lang } from '$lib/i18n';
	import { SCAN_NEAR, SCAN_DIP, FUNDING_HOT, FUNDING_COLD, NEAR_HIGH, DEEP_DD } from '$lib/scan';
	import { HOUSE_COINS } from '$lib/growth';
	import Callout from '$lib/components/callout.svelte';

	let { data }: { data: PageData } = $props();
	const lang = $derived<Lang>(data.lang ?? 'zh');
	const en = $derived(lang === 'en');
	/** Pick the string for the active language (each rendering stays single-language). */
	const tx = (zh: string, enText: string) => (en ? enText : zh);
	const p = (x: number) => `${Math.round(Math.abs(x) * 100)}%`;
	const coins = $derived(HOUSE_COINS.join(en ? ', ' : '、'));

	const SECTIONS = [
		['rules', '规则', 'The rules'],
		['costs', '成本', 'Costs'],
		['data', '数据来源', 'Data sources'],
		['coins', '币种怎么选', 'How the coins were picked'],
		['rejected', '测过、否决了', 'Tested and rejected'],
		['changelog', '更新记录', 'Changelog']
	] as const;

	type Row = string[];
	const universe: Row[] = [
		['选出的 13 个|Selected 13', '+48.5%', '+34.2%', '−31.3%', '−59.4%', '9/13'],
		['没选上的 9 个|Rejected 9', '+24.6%', '+31.0%', '−35.3%', '−56.2%', '3/9'],
		['原来的 BTC/ETH/SOL|Old set BTC/ETH/SOL', '+5.0%', '−5.4%', '−25.0%', '−51.3%', '3/3']
	];
	const carry: Row[] = [
		['BTC 一直持有|BTC always-on', '+11.7%', '+5.1%', '+2.7%'],
		['ETH 一直持有|ETH always-on', '+12.8%', '+4.9%', '+1.6%'],
		['SOL 一直持有|SOL always-on', '+13.4%', '+0.4%', '−1.4%'],
		['每周追费率最高 3 个|Weekly top-3 by funding', '+11.7%', '−1.7%', '−3.9%'],
		['每周追费率最高 10 个|Weekly top-10 by funding', '+6.6%', '−3.6%', '−5.5%']
	];
	const daily: Row[] = [
		['48 只美股|48 US equities', '+106.6%', '+261.1%', '10/46'],
		['12 种商品期货|12 commodity futures', '+0.9%', '+51.8%', '0/12']
	];
	const cell = (c: string) => (c.includes('|') ? (en ? c.split('|')[1] : c.split('|')[0]) : c);

	const CHANGELOG: { date: string; zh: string[]; en: string[] }[] = [
		{
			date: '2026-09-27',
			zh: [
				'币种从 3 个扩到 13 个(只用 2024–2025 年数据筛选,2026 年是样本外)。',
				'上线机会雷达(/scan)和每天早上 8:30 的 Telegram 早报。',
				'资金费率改为「情绪/拥挤度指标」展示,不再当套利机会(回测见上)。',
				'测试了 18 种趋势过滤器,没有一个稳定有效,规则不改。',
				'美股和大宗商品只做观察,不给买卖点(日线突破回测跑输长期持有)。'
			],
			en: [
				'Coin universe widened from 3 to 13 (selected on 2024–2025 data only; 2026 is out of sample).',
				'Opportunity radar (/scan) and a 08:30 Beijing-time Telegram digest went live.',
				'Funding is shown as a crowding / sentiment gauge, no longer as a carry opportunity (backtest above).',
				'Tested 18 trend filters; none held up, so the rule is unchanged.',
				'US equities and commodities are observation-only, with no buy/sell points (the daily breakout lost to buy-and-hold).'
			]
		},
		{
			date: '2026-09-26',
			zh: [
				'离场信号和每周战绩改为可转发的分享卡片。',
				'上线「定投加倍日」提醒(恐慌或大跌时按规则多买)。'
			],
			en: [
				'Exit signals and the weekly scorecard became shareable image cards.',
				'"DCA boost day" alerts went live (the rule buys more in fear or after a deep drop).'
			]
		},
		{
			date: '2026-09-25',
			zh: [
				'趋势突破信号在 BTC、ETH、SOL 上线,买入/离场实时推送到 Telegram。',
				'公开战绩页(/record):2026-01-01 起按规则回溯计算,标「回溯」。'
			],
			en: [
				'Trend-breakout signals went live on BTC, ETH and SOL, with buys and exits pushed to Telegram.',
				'Public track record (/record): replayed from 2026-01-01 with the same rule, labelled "Backfilled".'
			]
		}
	];
</script>

{#snippet table(head: string[], rows: Row[])}
	<div class="mt-3 overflow-x-auto rounded-lg border border-border">
		<table class="w-full text-left text-xs">
			<thead class="bg-secondary/50 text-muted-foreground">
				<tr>
					{#each head as h, i (i)}
						<th class="px-3 py-2 whitespace-nowrap {i ? 'text-right' : ''}">{h}</th>
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each rows as r, ri (ri)}
					<tr class="border-t border-border">
						{#each r as c, i (i)}
							<td
								class="px-3 py-2 {i
									? 'bdv-num text-right whitespace-nowrap'
									: 'font-medium text-foreground'}">{cell(c)}</td
							>
						{/each}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/snippet}

<svelte:head>
	<title>{tx('方法论', 'Methodology')} · BearDawnVerse Quant</title>
	<meta
		name="description"
		content={tx(
			'信号怎么算:趋势突破规则、智能定投、机会雷达阈值、手续费、数据来源、币种筛选,以及测过但否决的方案和更新记录。',
			'How the signals are made: the trend-breakout rule, smart DCA, radar thresholds, fees, data sources, coin selection, the ideas we tested and rejected, and a changelog.'
		)}
	/>
</svelte:head>

<main class="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
	<header>
		<div class="bdv-eyebrow mb-2 text-[var(--gold-500)]">
			{tx('规则公开 · 成本透明 · 失败也写出来', 'Open rules · honest costs · failures included')}
		</div>
		<h1 class="text-2xl font-bold tracking-tight sm:text-3xl">{tx('方法论', 'Methodology')}</h1>
		<p class="mt-3 text-sm leading-relaxed text-muted-foreground">
			{tx(
				'这里的每个信号都来自事先写死的规则,不是人工判断。下面写清楚规则是什么、成本怎么算、数据从哪来、币种怎么选,也写出了测过但没用的方案,以及每次改动的日期。',
				'Every signal here comes from a rule fixed in advance, not from anyone’s judgement. This page states the rules, how costs are counted, where the data comes from, how the coins were chosen, what we tested and did not adopt, and when anything changed.'
			)}
		</p>
		<nav class="mt-4 flex flex-wrap gap-2 text-xs">
			{#each SECTIONS as [id, zh, enLabel] (id)}
				<a
					href="#{id}"
					class="rounded-full border border-border px-3 py-1 text-muted-foreground hover:bg-accent hover:text-foreground"
					>{tx(zh, enLabel)}</a
				>
			{/each}
		</nav>
	</header>

	<!-- Rules -->
	<section id="rules" class="mt-10 scroll-mt-20">
		<h2 class="text-lg font-semibold tracking-tight">{tx('规则', 'The rules')}</h2>

		<h3 class="mt-4 text-sm font-semibold text-foreground">
			{tx('1. 趋势突破(策略买卖信号)', '1. Trend breakout (the buy/sell signals)')}
		</h3>
		<ul class="mt-2 flex list-disc flex-col gap-1.5 pl-5 text-sm text-muted-foreground">
			<li>
				{tx(
					'买入:币安现货 1 小时 K 线收盘价,高于之前 168 根(7 天)K 线的最高价。',
					'Buy: a Binance spot 1-hour close above the highest high of the previous 168 bars (7 days).'
				)}
			</li>
			<li>
				{tx(
					'卖出:持有期间,1 小时收盘价低于之前 72 根(3 天)K 线的最低价。',
					'Sell: while holding, a 1-hour close below the lowest low of the previous 72 bars (3 days).'
				)}
			</li>
			<li>
				{tx(
					'只看已经收盘的 K 线;当前这根不算进自己的回看窗口;同一根 K 线不会既买又卖。',
					'Only closed bars count; a bar is never part of its own lookback; one bar never both buys and sells.'
				)}
			</li>
			<li>
				{tx(
					`只做多、不加杠杆,每个币独立运行(${coins}),要么全仓持有,要么空仓。`,
					`Long only, no leverage; each coin runs on its own (${coins}), either fully in or flat.`
				)}
			</li>
			<li>
				{tx(
					'大多数信号会小亏离场,赚钱靠少数大行情:过去的胜率大约 4 成。',
					'Most signals exit with a small loss and a few big trends pay for them: the historical win rate is about 40%.'
				)}
			</li>
		</ul>

		<h3 class="mt-6 text-sm font-semibold text-foreground">
			{tx('2. 智能定投(定投加倍日)', '2. Smart DCA (boost days)')}
		</h3>
		<ul class="mt-2 flex list-disc flex-col gap-1.5 pl-5 text-sm text-muted-foreground">
			<li>
				{tx(
					'每天基础买 1 份 BTC。恐惧贪婪指数 ≤ 25 再加 3 份,≤ 15 改为加 5 份。',
					'One base unit of BTC a day. Fear & Greed ≤ 25 adds 3 units; ≤ 15 adds 5 instead.'
				)}
			</li>
			<li>
				{tx(
					'BTC 日线收盘比近 30 天最高价低 20% 以上,再加 2 份(可以和恐慌加仓叠加)。',
					'A daily close 20%+ below the 30-day high adds 2 more units (stacks with the fear add).'
				)}
			</li>
			<li>
				{tx(
					'加倍日提醒 7 天内最多推一次,除非倍数更高。恐慌可能持续很久,加倍不代表马上反弹。',
					'A boost-day alert goes out at most once per 7 days unless the multiple rises. Fear can last; a boost day is not a bottom call.'
				)}
			</li>
		</ul>

		<h3 class="mt-6 text-sm font-semibold text-foreground">
			{tx('3. 机会雷达的阈值', '3. Opportunity radar thresholds')}
		</h3>
		<ul class="mt-2 flex list-disc flex-col gap-1.5 pl-5 text-sm text-muted-foreground">
			<li>
				{tx(
					`接近买入触发:空仓中,现价距买入触发价 ${p(SCAN_NEAR)} 以内。接近离场线:持仓中,距离场线 ${p(SCAN_NEAR)} 以内。`,
					`Near a buy trigger: flat and within ${p(SCAN_NEAR)} of the trigger. Near the exit line: held and within ${p(SCAN_NEAR)} of it.`
				)}
			</li>
			<li>
				{tx(
					`大跌区:比 30 天最高价低 ${p(SCAN_DIP)} 以上。只是观察,不是买点。`,
					`Deep dip: ${p(SCAN_DIP)}+ below the 30-day high. An observation, not a buy point.`
				)}
			</li>
			<li>
				{tx(
					`资金费率(永续合约近 7 天实际费率年化):≥ +${p(FUNDING_HOT)}/年算多头拥挤,≤ −${p(FUNDING_COLD)}/年算空头拥挤。只当情绪指标。`,
					`Funding (last 7 days of actual perp funding, annualised): ≥ +${p(FUNDING_HOT)}/yr = crowded longs, ≤ −${p(FUNDING_COLD)}/yr = crowded shorts. A sentiment gauge only.`
				)}
			</li>
			<li>
				{tx(
					`美股和商品:距 52 周收盘高点 ${p(NEAR_HIGH)} 以内算接近高点,低 ${p(DEEP_DD)} 以上算深跌;另看是否站上 200 日均线和 VIX。只做观察。`,
					`US equities and commodities: within ${p(NEAR_HIGH)} of the 52-week closing high = near the high, ${p(DEEP_DD)}+ below = deep drawdown; plus the 200-day average and VIX. Observations only.`
				)}
			</li>
		</ul>
	</section>

	<!-- Costs -->
	<section id="costs" class="mt-10 scroll-mt-20">
		<h2 class="text-lg font-semibold tracking-tight">{tx('成本', 'Costs')}</h2>
		<ul class="mt-3 flex list-disc flex-col gap-1.5 pl-5 text-sm text-muted-foreground">
			<li>
				{tx(
					'每次买入、卖出各扣 0.1%(币安现货吃单费率),所以一买一卖约 0.2%。所有收益都是扣费后的。',
					'0.1% per buy and per sell (Binance spot taker fee), about 0.2% per round trip. Every return shown is after fees.'
				)}
			</li>
			<li>
				{tx(
					'按信号那根 K 线的收盘价成交,没有另算滑点;成交量小的币实际成交可能更差。',
					'Fills are assumed at the signal bar’s close with no extra slippage; thinly traded coins may fill worse in practice.'
				)}
			</li>
			<li>
				{tx(
					'还没卖出的持仓按最新 1 小时收盘价假设卖出,同样扣费。',
					'Open positions are marked as if sold at the latest 1-hour close, fees included.'
				)}
			</li>
			<li>
				{tx(
					'组合口径:资金平均分给每个币,各自跟随信号,中途不再平衡;对照组「买入持有」同样等分、同一时刻开始。',
					'Portfolio: money split equally across coins, each following its own signals, never rebalanced; the buy-and-hold comparison uses the same split and start.'
				)}
			</li>
		</ul>
	</section>

	<!-- Data -->
	<section id="data" class="mt-10 scroll-mt-20">
		<h2 class="text-lg font-semibold tracking-tight">{tx('数据来源', 'Data sources')}</h2>
		<ul class="mt-3 flex list-disc flex-col gap-1.5 pl-5 text-sm text-muted-foreground">
			<li>
				{tx(
					'加密货币价格:币安现货 1 小时 K 线(公开接口),每小时收盘后计算。',
					'Crypto prices: Binance spot 1-hour klines (public API), evaluated after every hourly close.'
				)}
			</li>
			<li>
				{tx(
					'资金费率:币安 USDT 永续合约的实际结算费率(成交额前 30 的合约 + 我们的 13 个币,只取现货也有的)。',
					'Funding: settled Binance USDT-perpetual funding (top 30 perps by volume plus our 13 coins, spot-listed only).'
				)}
			</li>
			<li>
				{tx(
					'恐惧贪婪指数:alternative.me;BTC 日线:币安。',
					'Fear & Greed: alternative.me; BTC daily bars: Binance.'
				)}
			</li>
			<li>
				{tx(
					'美股:Yahoo Finance 日线收盘(未做分红调整);商品:financialdata.net 连续期货日线(未做换月调整);VIX 来自我们的市场压力指数。',
					'US equities: Yahoo Finance daily closes (not dividend-adjusted); commodities: financialdata.net continuous futures (not roll-adjusted); VIX from our market stress index.'
				)}
			</li>
			<li>
				{tx(
					'所有外部数据都由我们的服务器抓取、存进自己的数据库,网页只读我们自己的接口。',
					'All upstream data is fetched by our servers into our own database; the site only reads our own API.'
				)}
			</li>
		</ul>
	</section>

	<!-- Coin selection -->
	<section id="coins" class="mt-10 scroll-mt-20">
		<h2 class="text-lg font-semibold tracking-tight">
			{tx('币种怎么选', 'How the coins were picked')}
		</h2>
		<p class="mt-3 text-sm leading-relaxed text-muted-foreground">
			{tx(
				'2026-09-27 从币安成交额前 30 的 USDT 交易对里筛选。只用 2024-01-01 到 2025-12-31 的数据,标准事先定好:两整年数据齐全、扣费后收益为正、最大回撤比买入持有浅、收益 / 最大回撤 ≥ 0.5。选出 13 个;BNB、LINK、ARB、DASH、QNT、RUNE、LTC、RARE、FIL 没过标准,ENA、TAO 等 8 个历史太短。',
				'Screened on 2026-09-27 from Binance’s top-30 USDT pairs by volume, using only 2024-01-01 to 2025-12-31 data with criteria fixed in advance: two full years of history, positive net return, a shallower max drawdown than buy-and-hold, and return / max drawdown ≥ 0.5. 13 passed; BNB, LINK, ARB, DASH, QNT, RUNE, LTC, RARE and FIL failed, and 8 coins such as ENA and TAO had too little history.'
			)}
		</p>
		<p class="mt-2 text-sm text-muted-foreground">
			{tx(
				'2026 年对这次筛选是样本外(2026-01-01 至 09-26,等权平均):',
				'2026 is out of sample for this screen (2026-01-01 to 09-26, equal-weight means):'
			)}
		</p>
		{@render table(
			[
				tx('分组', 'Group'),
				tx('策略', 'Strategy'),
				tx('买入持有', 'Buy & hold'),
				tx('策略最大回撤', 'Strategy max DD'),
				tx('持有最大回撤', 'Hold max DD'),
				tx('跑赢持有', 'Beat hold')
			],
			universe
		)}
		<p class="mt-3 text-sm text-muted-foreground">
			{tx(
				'老实说:平均数被 ZEC(+302%)拉高了;看中位数,策略 +6.6%、买入持有 −3.8%。亏损的也照样留着:WLD −56%、DOGE −23%、AVAX −13%。计划每年用新的样本重新筛一次。/record 上 2026 年的交易仍是回溯重放,不是当时发出的信号。',
				'Honestly: the means are pulled up by ZEC (+302%); the medians are strategy +6.6% vs hold −3.8%. Losers stay in: WLD −56%, DOGE −23%, AVAX −13%. We plan to re-screen once a year on fresh data. The 2026 trades on /record are still a replay, not calls made at the time.'
			)}
		</p>
	</section>

	<!-- Rejected -->
	<section id="rejected" class="mt-10 scroll-mt-20">
		<h2 class="text-lg font-semibold tracking-tight">
			{tx('测过、否决了', 'Tested and rejected')}
		</h2>

		<h3 class="mt-4 text-sm font-semibold text-foreground">
			{tx('资金费率套利(现货多 + 永续空)', 'Funding carry (long spot + short perp)')}
		</h3>
		<p class="mt-2 text-sm text-muted-foreground">
			{tx(
				'币安 2024-01 至 2026-09 的实际费率,成本按一进一出 0.40% 算(4 次吃单 + 价差);下表是按名义本金的年化收益,1:1 保证金时资金回报只有一半。',
				'Binance funding 2024-01 to 2026-09, costs 0.40% per round trip (4 taker fees + spread); returns below are annualised on notional — with 1:1 collateral the return on capital is half.'
			)}
		</p>
		{@render table([tx('做法', 'Variant'), '2024', '2025', tx('2026 至今', '2026 YTD')], carry)}
		<p class="mt-3 text-sm text-muted-foreground">
			{tx(
				'只有 2024 年牛市狂热时赚钱。2026 年主流币的资金回报约 1–1.5%,还不如闲置稳定币;追着高费率换仓扣费后是亏的——高费率几天内就回落,频繁换仓把收益吃光。所以雷达和早报只把资金费率当拥挤度指标。等 BTC/ETH 费率重新持续高于 15%/年再重新评估。',
				'Only the 2024 bull-market froth paid. In 2026 the majors return about 1–1.5% on capital, below idle stablecoin yield, and chasing high funding loses after fees — high funding mean-reverts within days and turnover eats it. So the radar and the digest treat funding as a crowding gauge only. We will revisit if BTC/ETH funding stays above 15%/yr.'
			)}
		</p>

		<h3 class="mt-6 text-sm font-semibold text-foreground">
			{tx('给趋势规则加过滤器', 'Filters on the trend rule')}
		</h3>
		<p class="mt-2 text-sm text-muted-foreground">
			{tx(
				'想减少震荡市里的假突破,试了 6 类共 18 种简单过滤(均线趋势、BTC 大盘过滤、突破幅度、ATR、亏损后冷却期、更长的突破窗口),参数事先定好,用 2022–2025 年选、2026 年验证。只有「亏损后冷却 72 小时」勉强过了样本内的标准(胜率只高 0.3 个百分点);样本外 13 个币里只有 3 个变好、2 个变差、8 个没区别,胜率一样是 43%。各年份方向也不一致,是噪音不是规律,所以规则不改。',
				'To cut false breakouts in ranging markets we tried 6 families, 18 simple filters in total (trend moving average, a BTC market gate, breakout strength, ATR, a cooldown after a loss, a longer breakout window), parameters fixed in advance, selected on 2022–2025 and checked on 2026. Only "72-hour cooldown after a loss" barely passed in sample (+0.3 points of win rate); out of sample it helped 3 of 13 coins, hurt 2 and tied 8, with the same 43% win rate. The direction flips from year to year — noise, not an edge — so the rule stays as it is.'
			)}
		</p>

		<h3 class="mt-6 text-sm font-semibold text-foreground">
			{tx('美股和商品的日线突破', 'Daily breakout on US equities and commodities')}
		</h3>
		<p class="mt-2 text-sm text-muted-foreground">
			{tx(
				'同类规则(只做多、次日成交、扣费)在历史上选参数,再看 2024-01 至 2026-09 的样本外:',
				'The same kind of rule (long only, next-day fill, net of fees), parameters picked on earlier history, then checked out of sample 2024-01 to 2026-09:'
			)}
		</p>
		{@render table(
			[
				tx('市场', 'Market'),
				tx('策略', 'Strategy'),
				tx('买入持有', 'Buy & hold'),
				tx('跑赢持有', 'Beat hold')
			],
			daily
		)}
		<p class="mt-3 text-sm text-muted-foreground">
			{tx(
				'两边都明显跑输长期持有,所以 /scan 的美股和商品只显示位置观察(离 52 周高点多远、是否站上 200 日均线、VIX),不给买卖点。',
				'Both clearly lost to buy-and-hold, so the equity and commodity tabs on /scan show observations only (distance from the 52-week high, the 200-day average, VIX) and never a buy or sell point.'
			)}
		</p>
	</section>

	<Callout type="info" title={tx('实时和回溯', 'Live vs backfilled')}>
		<p>
			{tx(
				'服务上线前的交易是用同一条规则在历史行情上重放算出来的,标「回溯」,当时没有推送给任何人。上线后的信号标「实时」,每小时收盘后立即记录并推送。战绩页把「上线以来的实时信号」单独列出来。「我的跟单」按信号价格和手续费计算,不是你的真实成交。',
				'Trades before launch were replayed on history with the same rule and are labelled "Backfilled": nobody was sent them at the time. Signals after launch are "Live", recorded and pushed right after each hourly close. The track record lists "Live signals since launch" separately. "My follows" is computed at signal prices and fees, not your real fills.'
			)}
		</p>
	</Callout>

	<!-- Changelog -->
	<section id="changelog" class="mt-10 scroll-mt-20">
		<h2 class="text-lg font-semibold tracking-tight">{tx('更新记录', 'Changelog')}</h2>
		<ol class="mt-4 flex flex-col gap-5 border-l border-border pl-5">
			{#each CHANGELOG as c (c.date)}
				<li>
					<div class="bdv-num text-sm font-semibold text-foreground">{c.date}</div>
					<ul class="mt-1.5 flex list-disc flex-col gap-1 pl-5 text-sm text-muted-foreground">
						{#each en ? c.en : c.zh as line, i (i)}
							<li>{line}</li>
						{/each}
					</ul>
				</li>
			{/each}
		</ol>
	</section>

	<p class="mt-10 flex flex-wrap gap-x-4 gap-y-2 text-sm">
		<a href={resolve('/record')} class="font-medium text-primary hover:underline"
			>{tx('策略战绩 →', 'Track record →')}</a
		>
		<a href={resolve('/scan')} class="font-medium text-primary hover:underline"
			>{tx('机会雷达 →', 'Opportunity radar →')}</a
		>
	</p>
	<p class="mt-4 text-xs text-muted-foreground">
		⚠️ {tx(
			'规则模拟信号,不构成投资建议。我们不代客理财,也不提供仓位建议;过往表现不代表未来收益。',
			'Rule-based simulated signals, not investment advice. We do not manage money or give position sizing advice; past performance does not predict future returns.'
		)}
	</p>
</main>
