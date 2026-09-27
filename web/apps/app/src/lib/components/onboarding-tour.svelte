<script lang="ts">
	// First-login onboarding tour — a centered modal wizard that tells the
	// product story (honest framing: tools + transparent data, no advice).
	// Auto-shows ~800ms after mount for logged-in users who haven't seen it
	// (localStorage flag); other pages can force it open via the tourOpen
	// store in $lib/tour. ESC/skip/finish/deep-link all mark it done.
	// Backdrop clicks do NOT close it (prevents accidental dismissal).
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/stores';
	import { session } from '$lib/auth';
	import { tourOpen } from '$lib/tour';
	import { type Lang } from '$lib/i18n';

	const lang = $derived<Lang>($page.data.lang ?? 'zh');
	const en = $derived(lang === 'en');

	const DONE_KEY = 'qt_tour_done';

	// In-app pages a tour step can deep-link to (typed so goto() goes through resolve()).
	type TourLink = '/backtest' | '/dca' | '/nautilus';

	interface TourStep {
		emoji: string;
		link?: TourLink;
		zh: { title: string; body: string };
		en: { title: string; body: string };
	}

	const steps: TourStep[] = [
		{
			emoji: '👋',
			zh: {
				title: '欢迎来到 BearDawnVerse Quant',
				body: '先说清楚:这里不荐股、不带单。这里给你的是验证工具和透明数据 —— 判断永远是你自己的。'
			},
			en: {
				title: 'Welcome to BearDawnVerse Quant',
				body: 'Up front: no stock picks, no trade-copying. What you get here are verification tools and transparent data — the judgment is always yours.'
			}
		},
		{
			emoji: '🧪',
			link: '/backtest',
			zh: {
				title: '验证一个策略',
				body: '免代码跑真实回测:选个推荐配置,~30 秒看到 10 年历史上它到底赚不赚钱(包括最大回撤)。'
			},
			en: {
				title: 'Verify a strategy',
				body: 'Run a real backtest with zero code: pick a recommended config and in ~30 seconds see whether it actually made money over 10 years of history — max drawdown included.'
			}
		},
		{
			emoji: '🔔',
			link: '/backtest',
			zh: {
				title: '变成你的实时信号',
				body: '回测满意?一键变成实时信号。绑定 Telegram 后,你的规则触发时手机收到提醒 —— 是你自己设定的规则,不是我们的建议。'
			},
			en: {
				title: 'Turn it into your live signal',
				body: 'Happy with a backtest? Turn it into a live signal in one click. Bind Telegram and your phone pings when your rules fire — your own rules, not our advice.'
			}
		},
		{
			emoji: '📒',
			link: '/dca',
			zh: {
				title: '管住手的定投教练',
				body: '定投最难的是坚持。存一个计划,每月提醒你执行,记一笔账,看真实均价和"比一把梭哈省了多少"。'
			},
			en: {
				title: 'A DCA coach that keeps your hands steady',
				body: 'The hardest part of DCA is sticking to it. Save a plan, get a monthly nudge to execute, log each buy, and see your true average cost — and how much you saved vs going all-in.'
			}
		},
		{
			emoji: '👀',
			link: '/nautilus',
			zh: {
				title: '围观真实机器人',
				body: '我们自己的策略 7×24 在模拟盘/测试网交易,每笔成交和每日账户净值全部公开 —— 不可伪造。'
			},
			en: {
				title: 'Watch real bots',
				body: 'Our own strategies trade 24/7 on paper/testnet accounts. Every fill and every daily account value is public — impossible to fake.'
			}
		}
	];

	let visible = $state(false);
	let step = $state(0);
	let cardEl = $state<HTMLDivElement | null>(null);

	const cur = $derived(steps[step]);
	const last = $derived(step === steps.length - 1);

	// Auto-show ~800ms after a session appears, unless already done.
	$effect(() => {
		if (!browser || !$session) return;
		if (localStorage.getItem(DONE_KEY) === '1') return;
		const t = setTimeout(() => {
			step = 0;
			visible = true;
		}, 800);
		return () => clearTimeout(t);
	});

	// Manual relaunch (e.g. the replay button on /start) — ignores the flag.
	$effect(() => {
		if ($tourOpen) {
			step = 0;
			visible = true;
		}
	});

	// Move focus into the dialog whenever it opens.
	$effect(() => {
		if (visible) cardEl?.focus();
	});

	function markDone() {
		if (browser) localStorage.setItem(DONE_KEY, '1');
	}

	function close() {
		visible = false;
		tourOpen.set(false);
	}

	function dismiss() {
		markDone();
		close();
	}

	function visit(href: TourLink) {
		markDone();
		close();
		void goto(resolve(href));
	}
</script>

<svelte:window
	onkeydown={(e) => {
		if (visible && e.key === 'Escape') dismiss();
	}}
/>

{#if visible}
	<!-- Backdrop intentionally has no click handler: no accidental dismiss. -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
		<div
			bind:this={cardEl}
			role="dialog"
			aria-modal="true"
			aria-labelledby="tour-title"
			tabindex="-1"
			class="relative w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-xl outline-none"
		>
			<button
				type="button"
				onclick={dismiss}
				class="absolute top-4 right-4 text-sm text-muted-foreground transition-colors hover:text-foreground"
			>
				{en ? 'Skip' : '跳过'}
			</button>

			<div class="text-4xl" aria-hidden="true">{cur.emoji}</div>
			<h2 id="tour-title" class="mt-3 pr-12 text-lg font-bold tracking-tight">
				{en ? cur.en.title : cur.zh.title}
			</h2>
			<p class="mt-2 text-sm leading-relaxed text-muted-foreground">
				{en ? cur.en.body : cur.zh.body}
			</p>

			{#if cur.link}
				{@const link = cur.link}
				<button
					type="button"
					onclick={() => visit(link)}
					class="mt-3 text-sm font-medium text-primary hover:underline"
				>
					{en ? 'Take a look →' : '去看看 →'}
				</button>
			{/if}

			<div class="mt-6 flex items-center justify-between gap-3">
				<div class="flex items-center gap-1.5" aria-hidden="true">
					{#each steps, i (i)}
						<span class={`h-1.5 w-1.5 rounded-full ${i === step ? 'bg-primary' : 'bg-border'}`}
						></span>
					{/each}
				</div>
				<div class="flex items-center gap-2">
					{#if step > 0}
						<button
							type="button"
							onclick={() => (step -= 1)}
							class="rounded-md border border-border px-3 py-1.5 text-sm transition-colors hover:bg-accent"
						>
							{en ? 'Back' : '上一步'}
						</button>
					{/if}
					{#if last}
						<button
							type="button"
							onclick={() => visit('/backtest')}
							class="rounded-md bg-primary px-4 py-1.5 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
						>
							{en ? 'Run your first backtest →' : '去跑第一个回测 →'}
						</button>
					{:else}
						<button
							type="button"
							onclick={() => (step += 1)}
							class="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
						>
							{en ? 'Next' : '下一步'}
						</button>
					{/if}
				</div>
			</div>
		</div>
	</div>
{/if}
