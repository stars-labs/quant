<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		type?: 'info' | 'warning' | 'success' | 'danger';
		title?: string;
		children?: Snippet;
	}
	const { type = 'info', title = '', children }: Props = $props();

	const cls = {
		info: 'border-l-[var(--violet-500)] bg-[color-mix(in_oklab,var(--violet-500)_8%,transparent)]',
		warning: 'border-l-[var(--warn)] bg-[color-mix(in_oklab,var(--warn)_10%,transparent)]',
		success: 'border-l-[var(--profit)] bg-[color-mix(in_oklab,var(--profit)_10%,transparent)]',
		danger: 'border-l-[var(--danger)] bg-[color-mix(in_oklab,var(--danger)_10%,transparent)]'
	}[type];
	const titleColor = {
		info: 'text-[var(--violet-500)]',
		warning: 'text-[var(--warn)]',
		success: 'text-[var(--profit)]',
		danger: 'text-[var(--danger)]'
	}[type];
</script>

<div class="my-4 rounded-md border border-l-4 border-border px-4 py-3.5 {cls}">
	{#if title}
		<div class="mb-1 text-[13px] font-semibold {titleColor}">{title}</div>
	{/if}
	<div class="text-[13px] leading-[1.55] text-muted-foreground">
		{@render children?.()}
	</div>
</div>
