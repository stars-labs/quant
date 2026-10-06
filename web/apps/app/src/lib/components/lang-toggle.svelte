<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import type { Lang } from '$lib/i18n';

	let { lang }: { lang: Lang } = $props();
	let busy = $state(false);
	let failed = $state(false);

	async function setLang(next: Lang) {
		if (next === lang || busy) return;
		busy = true;
		failed = false;
		// 1 year, site-wide; no Secure in dev but fine — this isn't sensitive.
		document.cookie = `lang=${next}; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax`;
		// Re-run all SSR loads so pages pick up the new cookie, without a hard nav.
		try {
			await invalidateAll();
		} catch {
			failed = true;
		} finally {
			busy = false;
		}
	}
</script>

<div
	class="flex items-center rounded-md border border-border bg-secondary p-0.5 text-[11px]"
	aria-busy={busy}
>
	<button
		type="button"
		onclick={() => setLang('zh')}
		aria-pressed={lang === 'zh'}
		disabled={busy}
		class="rounded px-2 py-0.5 transition-colors"
		class:bg-primary={lang === 'zh'}
		class:text-primary-foreground={lang === 'zh'}
		class:text-muted-foreground={lang !== 'zh'}>中</button
	>
	<button
		type="button"
		onclick={() => setLang('en')}
		aria-pressed={lang === 'en'}
		disabled={busy}
		class="rounded px-2 py-0.5 transition-colors"
		class:bg-primary={lang === 'en'}
		class:text-primary-foreground={lang === 'en'}
		class:text-muted-foreground={lang !== 'en'}>EN</button
	>
</div>
{#if busy}<span role="status" class="sr-only"
		>{lang === 'zh' ? '正在切换语言' : 'Switching language'}</span
	>{/if}
{#if failed}<span role="alert" class="text-xs text-red-500"
		>{lang === 'zh' ? '切换失败，请刷新重试' : 'Could not switch. Refresh to retry.'}</span
	>{/if}
