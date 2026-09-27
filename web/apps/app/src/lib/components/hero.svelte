<script lang="ts">
	// Top-of-home conversion hero. Shown to everyone (the anon GreetingBanner is empty, so
	// without this a first-time visitor lands on a wall of KPIs with no value prop). States
	// what the platform is and drives to the backtest playground — the differentiating action.
	import { page } from '$app/stores';
	import { session } from '$lib/auth';
	import { type Lang } from '$lib/i18n';
	const lang = $derived<Lang>($page.data.lang ?? 'zh');
	const en = $derived(lang === 'en');
</script>

<section
	class="mb-8 overflow-hidden rounded-2xl border bg-gradient-to-br from-primary/10 via-card to-card p-6 sm:p-8"
>
	<div class="max-w-3xl">
		<p class="text-xs font-medium tracking-wide text-primary uppercase">
			{en ? 'Open quant research platform' : '开放量化研究平台'}
		</p>
		<h1 class="mt-2 text-2xl font-bold tracking-tight sm:text-3xl">
			{en
				? 'Backtest your own strategies — see what actually works.'
				: '回测你自己的策略 —— 看什么真的有效。'}
		</h1>
		<p class="mt-3 text-sm text-muted-foreground sm:text-base">
			{en
				? 'Run real backtests on crypto & US equities with your own parameters, right in your browser. Honest drawdowns, live signals, open source — no spreadsheet, no install.'
				: '用你自己的参数,直接在浏览器里对加密货币和美股跑真实回测。诚实回撤、实时信号、开源 —— 不用表格、不用安装。'}
		</p>
		<div class="mt-5 flex flex-wrap gap-3">
			<a
				href="/backtest"
				class="rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
			>
				{en ? 'Try the backtest playground →' : '去回测实验室 →'}
			</a>
			{#if !$session}
				<a
					href="/login?next=/backtest"
					class="rounded-md border border-border bg-background px-5 py-2.5 text-sm font-medium transition-colors hover:bg-accent"
				>
					{en ? 'Sign in' : '登录'}
				</a>
			{/if}
			<a
				href="/strategies"
				class="rounded-md border border-border bg-background px-5 py-2.5 text-sm font-medium transition-colors hover:bg-accent"
			>
				{en ? 'Browse strategies' : '看策略'}
			</a>
			<a
				href="/start"
				class="rounded-md border border-border bg-background px-5 py-2.5 text-sm font-medium transition-colors hover:bg-accent"
			>
				{en ? 'New here? →' : '我是新手 →'}
			</a>
		</div>
		<p class="mt-4 text-xs text-muted-foreground">
			{en
				? '3 strategy families · real split-adjusted data · results private to your account'
				: '3 类策略 · 真实复权数据 · 结果仅你的账号可见'}
		</p>
	</div>
</section>
