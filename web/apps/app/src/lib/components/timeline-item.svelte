<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		title: string;
		date?: string;
		color?: string;
		children?: Snippet;
	}
	const { title, date = '', color = 'var(--violet-500)', children }: Props = $props();
</script>

<div class="relative pl-7">
	<!-- Vertical connector line -->
	<div class="absolute top-0 bottom-0 left-2 w-px bg-border"></div>
	<!-- Dot -->
	<div
		class="absolute top-1 left-0 h-3 w-3 rounded-full ring-2 ring-background"
		style="background: {color}; box-shadow: 0 0 0 2px {color}, 0 0 8px {color};"
	></div>
	<!-- Content -->
	<div>
		<div class="text-sm font-semibold text-foreground">{title}</div>
		{#if date}
			<div class="bdv-num mt-0.5 text-[11px] text-muted-foreground">{date}</div>
		{/if}
		{#if children}
			<div class="mt-1 text-[13px] leading-[1.55] text-muted-foreground">
				{@render children()}
			</div>
		{/if}
	</div>
</div>
