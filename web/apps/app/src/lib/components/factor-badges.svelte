<script lang="ts">
	import { factorColor } from '$lib/strategies';
	let { factors, size = 'sm' }: { factors: string[] | null | undefined; size?: 'xs' | 'sm' } =
		$props();
	const cls = size === 'xs' ? 'px-1.5 py-0 text-[10px]' : 'px-2 py-0.5 text-[11px]';
</script>

{#if factors && factors.length}
	<div class="flex flex-wrap gap-1">
		{#each factors as t, _i (_i)}
			<span class="rounded border font-mono {cls} {factorColor(t)}">{t}</span>
		{/each}
	</div>
{/if}
