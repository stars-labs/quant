<script lang="ts">
	interface Props {
		label: string;
		value: string | number;
		sub?: string;
		tone?: 'default' | 'good' | 'bad' | 'warn';
		glow?: boolean;
	}
	let { label, value, sub = '', tone = 'default', glow = false }: Props = $props();

	const valColor = {
		default: 'text-foreground',
		good: 'text-[var(--profit)]',
		bad: 'text-[var(--loss)]',
		warn: 'text-[var(--warn)]'
	}[tone];

	// Dawn glow only on "default" tone (the canonical BDV emphasis); semantic
	// tones get a matching colored hairline instead so they stay distinguishable.
	const ringClass = {
		default: glow
			? 'border-[var(--dawn-glow)] shadow-[0_0_24px_rgba(255,138,92,0.16)]'
			: 'border-border',
		good: 'border-[color-mix(in_oklab,var(--profit)_35%,transparent)]',
		bad: 'border-[color-mix(in_oklab,var(--loss)_40%,transparent)]',
		warn: 'border-[color-mix(in_oklab,var(--warn)_40%,transparent)]'
	}[tone];
</script>

<div
	class="relative overflow-hidden rounded-md border bg-card p-4 {ringClass} shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
>
	<!-- Subtle top-down lightening overlay (faux specular) -->
	<div
		class="pointer-events-none absolute inset-0 bg-gradient-to-b from-white/[0.025] to-transparent"
	></div>

	<div class="relative">
		<div class="bdv-eyebrow">{label}</div>
		<div class="bdv-num mt-1.5 text-[26px] leading-none font-bold tracking-[-0.02em] {valColor}">
			{value}
		</div>
		{#if sub}
			<div class="bdv-num mt-2 text-[11px] font-medium text-muted-foreground">{sub}</div>
		{/if}
	</div>
</div>
