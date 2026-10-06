<script lang="ts">
	import { login, signup, loginWithGoogle } from '$lib/auth';
	import { page } from '$app/stores';
	import { t, type Lang } from '$lib/i18n';

	const lang = $derived<Lang>($page.data.lang ?? 'zh');
	const en = $derived(lang === 'en');
	const next = $derived($page.url.searchParams.get('next') ?? '/');
	// Only trust same-origin relative paths; reject absolute URLs to avoid open redirects.
	const safeNext = $derived(next.startsWith('/') && !next.startsWith('//') ? next : '/');
	const execution = $derived(safeNext === '/execution');

	function fmt(key: string, vars: Record<string, string>) {
		let s = t(lang, key);
		for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, v);
		return s;
	}
</script>

<svelte:head><title>{t(lang, 'login.title')} · Crypto Quant</title></svelte:head>

<main class="mx-auto mt-20 max-w-sm px-5">
	<h1 class="text-2xl font-semibold tracking-tight">{t(lang, 'login.title')}</h1>
	<p class="mt-2 text-sm text-muted-foreground">
		{execution
			? t(lang, 'web.sign_in_to_connect_your_local_runner_and_view_your_private_account_reports')
			: en
				? 'Sign in to view all strategy details.'
				: '登录后查看全部策略详情。'}
	</p>

	{#if safeNext !== '/'}
		<div class="mt-4 rounded-md border border-primary/50 bg-primary/5 p-3 text-xs">
			{#if execution}
				<div class="font-medium text-foreground">
					{t(lang, 'web.your_account_reports_are_visible_only_to_you')}
				</div>
				<div class="mt-1 text-muted-foreground">
					{t(lang, 'web.trading_and_exchange_credentials_stay_on_your_machine')}
				</div>
			{:else}
				<div class="font-medium text-foreground">{fmt('login.why', { path: safeNext })}</div>
				<div class="mt-1 text-muted-foreground">{t(lang, 'login.publicHint')}</div>
			{/if}
		</div>
	{/if}

	<button
		type="button"
		onclick={() => login(safeNext)}
		class="mt-6 w-full rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90"
	>
		{t(lang, 'login.submit')}
	</button>

	<button
		type="button"
		onclick={() => signup(safeNext)}
		class="mt-3 w-full rounded-md border border-border bg-background px-4 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
	>
		{t(lang, 'login.signup')}
	</button>

	<div class="my-5 flex items-center gap-3 text-[10px] text-muted-foreground uppercase">
		<span class="h-px flex-1 bg-border"></span>
		<span>{t(lang, 'login.or')}</span>
		<span class="h-px flex-1 bg-border"></span>
	</div>

	<button
		type="button"
		onclick={() => loginWithGoogle(safeNext)}
		class="flex w-full items-center justify-center gap-3 rounded-md border border-border bg-background px-4 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
	>
		<svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
			<path
				fill="#EA4335"
				d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
			/>
			<path
				fill="#4285F4"
				d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
			/>
			<path
				fill="#FBBC05"
				d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
			/>
			<path
				fill="#34A853"
				d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
			/>
		</svg>
		{t(lang, 'login.google')}
	</button>
	{#if !en}
		<p class="mt-1.5 text-center text-[11px] text-muted-foreground">
			需要科学上网（中国大陆需代理访问 Google）
		</p>
	{/if}

	<p class="mt-4 text-xs text-muted-foreground">
		{execution
			? t(lang, 'web.no_exchange_credentials_are_required_here')
			: en
				? 'Most pages are browseable without login.'
				: '未登录也能浏览大多数内容。'}
	</p>
</main>
