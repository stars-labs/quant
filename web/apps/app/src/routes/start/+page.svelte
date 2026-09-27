<script lang="ts">
	// 新手指南 — onboarding page for non-technical visitors. Answers "what is this /
	// what can I do here / how do I start" in plain language, with an honest framing
	// (no stock picks, no managed money). Static bilingual content; no server load.
	import { page } from '$app/stores';
	import { type Lang } from '$lib/i18n';
	import { tourOpen } from '$lib/tour';
	const lang = $derived<Lang>($page.data.lang ?? 'zh');
	const en = $derived(lang === 'en');
</script>

<svelte:head>
	<title>{en ? 'Getting started' : '新手指南'} · Crypto Quant</title>
	<meta
		name="description"
		content="新手指南：这个平台是什么、能做什么、如何开始——免代码回测、实时信号、公开账本，不荐股、不代客理财。"
	/>
	<meta property="og:title" content="{en ? 'Getting started' : '新手指南'} · Crypto Quant" />
	<meta
		property="og:description"
		content="新手指南：这个平台是什么、能做什么、如何开始——免代码回测、实时信号、公开账本，不荐股、不代客理财。"
	/>
</svelte:head>

<main class="mx-auto mt-12 max-w-3xl px-5 pb-16">
	<!-- H1 + honest opening -->
	<div class="flex flex-wrap items-center justify-between gap-3">
		<h1 class="text-2xl font-bold tracking-tight sm:text-3xl">
			{en ? 'This site in 3 minutes' : '三分钟搞懂这个站'}
		</h1>
		<button
			type="button"
			onclick={() => tourOpen.set(true)}
			class="rounded-md border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
		>
			👋 {en ? 'Replay the tour' : '重新看新手引导'}
		</button>
	</div>
	<p class="mt-4 text-sm leading-relaxed text-muted-foreground sm:text-base">
		{en
			? 'Let’s be clear up front: no stock picks, no trade-copying, no managing money for you. This is an open, transparent quant research site — you can see the real performance of real strategies (losses included), and verify everything yourself.'
			: '先说清楚:这里不荐股、不带单、不代客理财。这里是一个公开透明的量化研究站 —— 你能看到真实策略的真实表现(包括亏损),并亲手验证。'}
	</p>

	<!-- Three things you can do here -->
	<section class="mt-10">
		<h2 class="text-lg font-semibold tracking-tight">
			{en ? '3 things you can do here' : '你能在这里做的 3 件事'}
		</h2>
		<div class="mt-4 grid gap-4 sm:grid-cols-3">
			<div class="flex flex-col rounded-xl border border-border bg-card p-5">
				<div class="text-2xl" aria-hidden="true">🧪</div>
				<h3 class="mt-2 font-semibold">
					{en ? 'Verify a strategy' : '验证策略'}
				</h3>
				<p class="mt-1.5 flex-1 text-sm text-muted-foreground">
					{en
						? 'Run a real backtest with zero code — see whether an idea actually made money historically.'
						: '免代码跑真实回测,看一个想法历史上到底赚不赚钱。'}
				</p>
				<p class="mt-1.5 text-xs text-muted-foreground">
					{en
						? 'Happy with a backtest? Turn the config into a live signal alert in one click.'
						: '回测满意后,可以一键把配置变成实时信号提醒。'}
				</p>
				<a href="/backtest" class="mt-4 text-sm font-medium text-primary hover:underline">
					{en ? 'Run a backtest →' : '去跑回测 →'}
				</a>
			</div>
			<div class="flex flex-col rounded-xl border border-border bg-card p-5">
				<div class="text-2xl" aria-hidden="true">👀</div>
				<h3 class="mt-2 font-semibold">
					{en ? 'Watch real bots' : '围观真实机器人'}
				</h3>
				<p class="mt-1.5 flex-1 text-sm text-muted-foreground">
					{en
						? 'Our own strategies trade 24/7 on testnet / paper accounts — every single trade is public.'
						: '我们自己的策略 7×24 在测试网/模拟盘实时交易,每一笔都公开。'}
				</p>
				<a href="/nautilus" class="mt-4 text-sm font-medium text-primary hover:underline">
					{en ? 'See live execution →' : '看实时执行 →'}
				</a>
			</div>
			<div class="flex flex-col rounded-xl border border-border bg-card p-5">
				<div class="text-2xl" aria-hidden="true">📊</div>
				<h3 class="mt-2 font-semibold">
					{en ? 'Read market signals' : '看懂市场信号'}
				</h3>
				<p class="mt-1.5 flex-1 text-sm text-muted-foreground">
					{en
						? 'Fear & Greed index, flash-crash events, semiconductor supply-chain rotation.'
						: '恐惧贪婪指数、闪崩事件、半导体产业链轮动。'}
				</p>
				<a href="/signals" class="mt-4 text-sm font-medium text-primary hover:underline">
					{en ? 'Browse signals →' : '去看信号 →'}
				</a>
			</div>
		</div>
	</section>

	<!-- Signal glossary -->
	<section class="mt-12">
		<h2 class="text-lg font-semibold tracking-tight">
			{en ? 'Signal glossary' : '信号词典'}
		</h2>
		<p class="mt-1.5 text-sm text-muted-foreground">
			{en
				? 'The jargon you’ll see around the site, in plain words — and how we actually use each one.'
				: '站内会反复出现的术语,用白话讲清楚 —— 以及我们实际怎么用它。'}
		</p>
		<div class="mt-4 flex flex-col gap-3">
			<div class="rounded-md border border-border bg-card p-4">
				<div class="font-mono text-sm font-semibold text-primary">FLASH</div>
				<p class="mt-1 text-sm">
					{en
						? 'Flash crash: price drops sharply in a very short window — a moment of panic. Historically these have tended to be DCA add-on points rather than capitulation points.'
						: '闪崩:价格短时间急跌,恐慌时刻。历史上往往是定投加仓点而非割肉点。'}
				</p>
				<p class="mt-1 text-sm text-muted-foreground">
					{en
						? 'How we use it: our signal layer detects it and notifies; the smart-DCA strategy treats it as a candidate add-on trigger in backtests.'
						: '我们怎么用它:信号系统检测到后推送提醒,智能定投策略在回测里把它作为加仓触发条件之一。'}
				</p>
			</div>
			<div class="rounded-md border border-border bg-card p-4">
				<div class="font-mono text-sm font-semibold text-primary">FAST</div>
				<p class="mt-1 text-sm">
					{en
						? 'Fast decline: the downtrend is accelerating — the system raises its attention level.'
						: '快速下跌:跌势加速,系统提高关注。'}
				</p>
				<p class="mt-1 text-sm text-muted-foreground">
					{en
						? 'How we use it: an early-warning tier — it escalates monitoring before anything stronger fires.'
						: '我们怎么用它:作为预警级别,在更强信号触发前先升级监控。'}
				</p>
			</div>
			<div class="rounded-md border border-border bg-card p-4">
				<div class="font-mono text-sm font-semibold text-primary">SUSTAIN</div>
				<p class="mt-1 text-sm">
					{en
						? 'Sustained grind-down: multiple consecutive days of decline — the phase that wears out your patience.'
						: '持续阴跌:连续多日下行,消耗耐心的阶段。'}
				</p>
				<p class="mt-1 text-sm text-muted-foreground">
					{en
						? 'How we use it: to distinguish a slow grind from a sharp crash, so strategies don’t keep buying dips that aren’t done dipping.'
						: '我们怎么用它:区分"阴跌"和"急跌",避免策略在没跌完的行情里反复抄底。'}
				</p>
			</div>
			<div class="rounded-md border border-border bg-card p-4">
				<div class="font-mono text-sm font-semibold text-primary">CAPITUL</div>
				<p class="mt-1 text-sm">
					{en
						? 'Capitulation: panic peaks and volume spikes as holders give up — major bottoms have often formed here historically.'
						: '投降式抛售:恐慌见顶,成交放量,历史大底常见于此。'}
				</p>
				<p class="mt-1 text-sm text-muted-foreground">
					{en
						? 'How we use it: the highest-severity signal tier; in backtests the smart-DCA sizes its largest add-ons here.'
						: '我们怎么用它:最高级别的信号;回测中智能定投在这里的加仓力度最大。'}
				</p>
			</div>
			<div class="rounded-md border border-border bg-card p-4">
				<div class="font-mono text-sm font-semibold text-primary">
					{en ? 'FNG (Fear & Greed index)' : 'FNG 恐惧贪婪指数'}
				</div>
				<p class="mt-1 text-sm">
					{en
						? 'A 0–100 market-mood gauge — the lower, the more fearful the market.'
						: '0-100 的市场情绪指标,越低越恐慌。'}
				</p>
				<p class="mt-1 text-sm text-muted-foreground">
					{en
						? 'How we use it: our smart-DCA automatically sizes up purchases when fear is high and scales back when greed is high.'
						: '我们怎么用它:我们的智能定投在恐慌时自动加码、贪婪时自动减少买入。'}
				</p>
			</div>
			<div class="rounded-md border border-border bg-card p-4">
				<div class="font-mono text-sm font-semibold text-primary">
					{en ? 'EMA golden / death cross' : 'EMA 金叉/死叉'}
				</div>
				<p class="mt-1 text-sm">
					{en
						? 'A fast moving average crossing a slow one — up is a "golden cross", down is a "death cross".'
						: '快均线穿过慢均线:向上叫金叉,向下叫死叉。'}
				</p>
				<p class="mt-1 text-sm text-muted-foreground">
					{en
						? 'How we use it: it is the entry/exit signal of our trend-following strategies.'
						: '我们怎么用它:这是我们趋势策略的进出场信号。'}
				</p>
			</div>
			<div class="rounded-md border border-border bg-card p-4">
				<div class="font-mono text-sm font-semibold text-primary">
					{en ? 'Max drawdown' : '最大回撤'}
				</div>
				<p class="mt-1 text-sm">
					{en
						? 'The biggest peak-to-trough fall — the number that decides whether you can actually hold a strategy. It matters more than the return.'
						: '从最高点跌下来的最大幅度 —— 这是你拿不拿得住的关键数字,比收益率更重要。'}
				</p>
				<p class="mt-1 text-sm text-muted-foreground">
					{en
						? 'How we use it: every backtest report on this site shows it up front — no hiding the pain.'
						: '我们怎么用它:站内每份回测报告都把它放在最显眼的位置 —— 不藏疼痛。'}
				</p>
			</div>
			<div class="rounded-md border border-border bg-card p-4">
				<div class="font-mono text-sm font-semibold text-primary">Sharpe</div>
				<p class="mt-1 text-sm">
					{en
						? 'How much return you earn per unit of volatility you endure — above 1 is decent.'
						: '每承担一份波动换来多少收益,>1 算不错。'}
				</p>
				<p class="mt-1 text-sm text-muted-foreground">
					{en
						? 'How we use it: to compare strategies on risk-adjusted terms instead of raw returns alone.'
						: '我们怎么用它:用它在"风险调整后"的口径下比较策略,而不是只看收益。'}
				</p>
			</div>
		</div>
		<p class="mt-3 text-xs text-muted-foreground">
			{en
				? 'These are explanations of terms, not recommendations. Nothing here constitutes investment advice.'
				: '以上是名词解释,不是操作建议。这不构成投资建议。'}
		</p>
		<p class="mt-3 text-sm text-muted-foreground">
			{#if en}
				Want a Telegram ping when one of these signals fires? Subscribe on the <a
					href="/dca"
					class="font-medium text-primary hover:underline">DCA page</a
				>
				or the
				<a href="/backtest" class="font-medium text-primary hover:underline">backtest page</a>.
			{:else}
				想在信号触发时收到 Telegram 通知?去<a
					href="/dca"
					class="font-medium text-primary hover:underline">定投页</a
				>或<a href="/backtest" class="font-medium text-primary hover:underline">回测页</a>订阅。
			{/if}
		</p>
	</section>

	<!-- Why we don't just tell you what to buy -->
	<section class="mt-12 rounded-2xl border border-border bg-card p-6">
		<h2 class="text-lg font-semibold tracking-tight">
			{en ? 'Why don’t you just tell me what to buy?' : '为什么不直接告诉我买什么?'}
		</h2>
		<p class="mt-3 text-sm leading-relaxed text-muted-foreground">
			{en
				? 'Two reasons. First, the legal red line: we do not pick stocks, signal trades to copy, or manage money for anyone — full stop. Second, the philosophy: anyone promising you certain returns is lying to you. What we can honestly offer is verification tools and a transparent track record — every strategy, every trade, every drawdown, in the open. The judgment stays yours.'
				: '两个原因。第一是法规红线:我们不荐股、不带单、不代客理财,没有例外。第二是哲学:凡是承诺确定收益的,都在骗你。我们能诚实给出的,是验证工具和透明记录 —— 每个策略、每笔交易、每次回撤都公开。判断,留给你自己。'}
		</p>
		<p class="mt-3 text-sm leading-relaxed text-muted-foreground">
			{#if en}
				We even publish our failed strategies — see the <a
					href="/graveyard"
					class="font-medium text-primary hover:underline">strategy graveyard</a
				>.
			{:else}
				我们连失败的策略都公开 —— 看<a
					href="/graveyard"
					class="font-medium text-primary hover:underline">策略墓地</a
				>。
			{/if}
		</p>
	</section>

	<!-- Footer CTA -->
	<div class="mt-10 flex justify-center">
		<a
			href="/backtest"
			class="rounded-md bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
		>
			{en ? 'Run your first backtest →' : '去跑第一个回测 →'}
		</a>
	</div>
</main>
