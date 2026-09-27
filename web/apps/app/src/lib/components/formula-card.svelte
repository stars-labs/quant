<script lang="ts">
	interface Props {
		label?: string;
		formula: string;
		note?: string;
	}
	const { label = '', formula, note = '' }: Props = $props();
</script>

<div
	class="my-4 rounded-md border border-border bg-card p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
>
	{#if label}
		<div class="bdv-eyebrow mb-2 text-[var(--hex-500)]">{label}</div>
	{/if}
	<div
		class="bdv-num mb-2 text-[13px] leading-relaxed font-bold whitespace-pre-wrap text-foreground"
	>
		{formula}
	</div>
	{#if note}
		<div class="text-[12px] leading-relaxed text-muted-foreground">{note}</div>
	{/if}
</div>
