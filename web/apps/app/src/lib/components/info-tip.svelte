<script lang="ts">
	// Lightweight hover tooltip — shows a small ⓘ marker next to a header/label
	// with a styled popup on hover/focus. No deps; CSS-only.
	let { text, placement = 'bottom' }: { text: string; placement?: 'top' | 'bottom' } = $props();
</script>

<span class="group relative ml-1 inline-flex cursor-help items-center align-middle">
	<span class="text-[10px] leading-none text-muted-foreground group-hover:text-foreground">ⓘ</span>
	<span
		class="pointer-events-none invisible absolute z-50 w-64 rounded-md border bg-popover px-3 py-2 text-[11px] leading-relaxed font-normal text-popover-foreground normal-case opacity-0 shadow-lg transition group-hover:visible group-hover:opacity-100 {placement ===
		'top'
			? 'bottom-full left-0 mb-1'
			: 'top-full left-0 mt-1'}"
	>
		{text}
	</span>
</span>
