<script lang="ts">
	interface Props {
		label: string;
		value: string;
		sub?: string;
		gradient?: boolean;
	}
	const { label, value, sub = '', gradient = true }: Props = $props();
</script>

<div
	class="relative overflow-hidden rounded-md border border-border bg-card p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
>
	<div
		class="pointer-events-none absolute inset-0 bg-gradient-to-b from-white/[0.025] to-transparent"
	></div>
	<div class="relative">
		<div class="bdv-eyebrow">{label}</div>
		{#if gradient}
			<div
				class="bdv-num bdv-grad-text mt-1.5 text-[22px] leading-none font-bold tracking-[-0.02em]"
			>
				{value}
			</div>
		{:else}
			<div
				class="bdv-num mt-1.5 text-[22px] leading-none font-bold tracking-[-0.02em] text-foreground"
			>
				{value}
			</div>
		{/if}
		{#if sub}
			<div class="mt-2 text-[11px] text-muted-foreground">{sub}</div>
		{/if}
	</div>
</div>
