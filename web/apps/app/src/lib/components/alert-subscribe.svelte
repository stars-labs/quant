<script lang="ts">
	// Telegram alert-subscription card — self-contained, drop anywhere.
	// Anonymous → one-line login prompt. Logged in → create link row → bind via
	// t.me deep link (an external dispatcher flips `bound`; we poll every 5s for
	// up to ~2 min) → pick topics (PATCH on change, optimistic).
	import { onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { user } from '$lib/auth';
	import { type Lang } from '$lib/i18n';
	import {
		getMyLink,
		createLink,
		updateTopics,
		TELEGRAM_BOT_URL,
		type TelegramLink,
		type TelegramTopic
	} from '$lib/alerts';
	import { track } from '$lib/track';

	const lang = $derived<Lang>($page.data.lang ?? 'zh');
	const en = $derived(lang === 'en');

	const TOPICS: { id: TelegramTopic; zh: string; en: string }[] = [
		{
			id: 'strategy_signals',
			zh: '策略买卖信号 — BTC/ETH/SOL 趋势突破买入与离场 + 每周战绩',
			en: 'Strategy buy/sell signals — BTC/ETH/SOL trend breakouts and exits + weekly scorecard'
		},
		{
			id: 'equity_trades',
			zh: '美股模拟盘交易 — 开仓/平仓通知',
			en: 'US-equity paper trades — open/close notifications'
		}
	];

	let link = $state<TelegramLink | null>(null);
	let loaded = $state(false);
	let busy = $state(false);
	let err = $state('');
	let saved = $state(false);
	let pollExpired = $state(false);

	// ── Bind polling: every 5s while the deep link is out, capped at ~2 min ──
	const POLL_MS = 5000;
	const POLL_MAX = 24;
	let pollTimer: ReturnType<typeof setInterval> | null = null;
	let pollCount = 0;

	function stopPolling() {
		if (pollTimer) {
			clearInterval(pollTimer);
			pollTimer = null;
		}
	}

	function startPolling() {
		stopPolling();
		pollExpired = false;
		pollCount = 0;
		pollTimer = setInterval(async () => {
			pollCount += 1;
			try {
				const wasBound = link?.bound === true;
				const l = await getMyLink();
				if (l) link = l;
				if (l?.bound) {
					stopPolling();
					if (!wasBound) track('telegram_bound');
				} else if (pollCount >= POLL_MAX) {
					stopPolling();
					pollExpired = true; // give up quietly; user gets a manual refresh button
				}
			} catch {
				// transient poll failure — keep trying until the cap
			}
		}, POLL_MS);
	}

	async function load() {
		try {
			link = await getMyLink();
			err = '';
			if (link && !link.bound) startPolling();
		} catch (e) {
			err = (e as Error).message;
		} finally {
			loaded = true;
		}
	}

	// Load whenever a user session appears; reset when it goes away.
	$effect(() => {
		if ($user?.sub) {
			void load();
		} else {
			link = null;
			loaded = false;
			stopPolling();
		}
	});

	onDestroy(stopPolling);

	async function subscribe() {
		const sub = $user?.sub;
		if (!sub || busy) return;
		busy = true;
		err = '';
		try {
			link = await createLink(sub);
			startPolling();
		} catch (e) {
			err = (e as Error).message;
		} finally {
			busy = false;
		}
	}

	async function refreshNow() {
		err = '';
		try {
			const wasBound = link?.bound === true;
			const l = await getMyLink();
			if (l) link = l;
			if (l?.bound && !wasBound) track('telegram_bound');
			if (l && !l.bound) startPolling(); // re-arm another 2-min window
		} catch (e) {
			err = (e as Error).message;
		}
	}

	let savedTimer: ReturnType<typeof setTimeout> | null = null;
	async function toggleTopic(id: TelegramTopic) {
		const sub = $user?.sub;
		const cur = link;
		if (!sub || !cur) return;
		const next = cur.topics.includes(id) ? cur.topics.filter((t) => t !== id) : [...cur.topics, id];
		link = { ...cur, topics: next }; // optimistic
		err = '';
		try {
			await updateTopics(sub, next);
			saved = true;
			if (savedTimer) clearTimeout(savedTimer);
			savedTimer = setTimeout(() => (saved = false), 2000);
		} catch (e) {
			link = cur; // revert
			err = (e as Error).message;
		}
	}
</script>

<!-- Both links carry runtime query strings (login ?next=, external t.me deep link). -->
<!-- eslint-disable svelte/no-navigation-without-resolve -->
<section class="rounded-xl border border-border bg-card p-5">
	{#if !$user}
		<p class="text-sm text-muted-foreground">
			🔔
			{en
				? 'Sign in to get a Telegram ping when signals fire.'
				: '登录后可在信号触发时收到 Telegram 通知。'}
			<a
				href={`/login?next=${encodeURIComponent($page.url.pathname)}`}
				class="font-medium text-primary hover:underline">{en ? 'Sign in →' : '登录 →'}</a
			>
		</p>
	{:else if !loaded}
		<p class="text-sm text-muted-foreground">{en ? 'Loading…' : '加载中…'}</p>
	{:else if !link}
		<div class="text-sm font-medium text-foreground">
			{en ? 'Telegram signal alerts' : 'Telegram 信号提醒'}
		</div>
		<p class="mt-1 text-sm text-muted-foreground">
			{en
				? 'Get a Telegram message the moment a strategy buy/sell signal or paper trade fires — no need to keep this page open.'
				: '策略发出买卖信号或模拟盘成交时，第一时间推送到你的 Telegram，不用一直盯着页面。'}
		</p>
		<button
			type="button"
			onclick={subscribe}
			disabled={busy}
			class="mt-3 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
		>
			🔔 {en ? 'Subscribe to signal alerts' : '订阅信号提醒'}
		</button>
	{:else if !link.bound}
		<div class="text-sm font-medium text-foreground">
			{en ? 'One step left: bind Telegram' : '还差一步：绑定 Telegram'}
		</div>
		<a
			href={`${TELEGRAM_BOT_URL}?start=${link.link_token}`}
			target="_blank"
			rel="noopener noreferrer"
			class="mt-3 inline-block rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90"
		>
			{en ? 'Bind in Telegram →' : '在 Telegram 中绑定 →'}
		</a>
		<p class="mt-2 text-xs text-muted-foreground">
			{en
				? 'Tap START after Telegram opens — that completes the binding.'
				: '打开 Telegram 后点 START 即完成绑定'}
		</p>
		{#if pollExpired}
			<button
				type="button"
				onclick={refreshNow}
				class="mt-2 rounded-md border border-border px-3 py-1.5 text-xs text-foreground hover:bg-muted/30"
			>
				{en ? 'Refresh' : '手动刷新'}
			</button>
		{:else}
			<p class="mt-2 animate-pulse text-xs text-muted-foreground">
				{en ? 'Waiting for the bind…' : '等待绑定中…'}
			</p>
		{/if}
	{:else}
		<div class="flex flex-wrap items-baseline gap-x-2">
			<span class="text-sm font-medium text-foreground"
				>✅ {en ? 'Telegram bound' : 'Telegram 已绑定'}</span
			>
			{#if saved}
				<span class="text-xs text-emerald-600">{en ? 'Saved' : '已保存'}</span>
			{/if}
		</div>
		<div class="mt-3 flex flex-col gap-2">
			{#each TOPICS as tp (tp.id)}
				<label class="flex items-start gap-2 text-sm">
					<input
						type="checkbox"
						checked={link.topics.includes(tp.id)}
						onchange={() => toggleTopic(tp.id)}
						class="mt-0.5 accent-primary"
					/>
					<span>{en ? tp.en : tp.zh}</span>
				</label>
			{/each}
		</div>
		<p class="mt-3 text-xs text-muted-foreground">
			{en
				? 'Automated signals — not investment advice. Untick anytime.'
				: '自动信号，不构成投资建议。可随时取消勾选。'}
		</p>
	{/if}
	{#if err}<p class="mt-2 text-xs text-red-500">{err}</p>{/if}
</section>
