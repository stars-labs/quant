<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { user } from '$lib/auth';
	import { getMyLink, createLink, TELEGRAM_BOT_URL, type TelegramLink } from '$lib/alerts';
	let { lang }: { lang: string } = $props();
	let link = $state<TelegramLink | null>(null);
	let busy = $state(false);
	let error = $state(false);
	async function refresh() {
		busy = true;
		try {
			link = await getMyLink();
			error = false;
		} catch {
			error = true;
		} finally {
			busy = false;
		}
	}
	async function connect() {
		busy = true;
		try {
			const id = get(user)?.sub;
			if (!id) throw new Error();
			// A private account connection does not enroll users into research topics.
			link = (await getMyLink()) ?? (await createLink(id, fetch, []));
			error = false;
		} catch {
			error = true;
		} finally {
			busy = false;
		}
	}
	onMount(() => {
		void refresh();
	});
</script>

<section class="mt-6 rounded-xl border border-border bg-card p-6">
	<h2 class="font-semibold">{lang === 'zh' ? '私有 Telegram 提醒' : 'Private Telegram alerts'}</h2>
	<p class="mt-2 text-sm text-muted-foreground">
		{lang === 'zh'
			? '绑定后，在机器人私聊中使用 /live 查看自己的账户，用 /livealerts on 开启成交和报告状态提醒，/livealerts off 关闭。'
			: 'After binding, use /live in the bot’s private chat to view your account. Use /livealerts on for fill and report-health alerts, or /livealerts off to disable them.'}
	</p>
	<p class="mt-2 text-xs text-muted-foreground">
		{lang === 'zh'
			? '其他用户默认不开启私有提醒。此设置不会启动或停止交易。'
			: 'Private alerts are off by default for other users. These settings do not start or stop trading.'}
	</p>
	<div class="mt-4 flex flex-wrap gap-3 text-sm">
		{#if link?.bound}
			<span>{lang === 'zh' ? 'Telegram 已绑定' : 'Telegram connected'}</span>
			<a class="text-primary" href={TELEGRAM_BOT_URL} target="_blank" rel="noopener noreferrer"
				>{lang === 'zh' ? '打开机器人' : 'Open bot'}</a
			>
		{:else if link}
			<a
				class="text-primary"
				href={`${TELEGRAM_BOT_URL}?start=${encodeURIComponent(link.link_token)}`}
				target="_blank"
				rel="noopener noreferrer"
				>{lang === 'zh' ? '打开 Telegram 并点 START' : 'Open Telegram and tap START'}</a
			>
		{:else}
			<button class="rounded border border-border px-3 py-2" disabled={busy} onclick={connect}
				>{lang === 'zh' ? '接入 Telegram' : 'Connect Telegram'}</button
			>
		{/if}
		<button class="rounded border border-border px-3 py-2" disabled={busy} onclick={refresh}
			>{lang === 'zh' ? '刷新绑定状态' : 'Refresh binding'}</button
		>
	</div>
	{#if error}<p class="mt-3 text-sm text-destructive" role="alert">
			{lang === 'zh'
				? '暂时无法更新绑定，请重新登录后重试。'
				: 'Binding could not be updated. Sign in again and retry.'}
		</p>{/if}
</section>
