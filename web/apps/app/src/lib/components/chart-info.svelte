<script lang="ts">
	import { getMetric } from '$lib/charts/glossary';
	import type { Lang } from '$lib/i18n';

	let {
		metric,
		lang,
		note,
		extraTitle,
		size = 'sm'
	}: {
		// Glossary key from $lib/charts/glossary. Missing keys silently render
		// the button as "?" so we don't ship broken UI when a key is added late.
		metric: string;
		lang: Lang;
		// Optional one-liner specific to *this* chart instance (e.g. "x = Sortino,
		// y = profit% — top-right is the sweet spot"). Appears below the rules.
		note?: string;
		// Override the popover title (defaults to the glossary entry's name).
		extraTitle?: string;
		size?: 'xs' | 'sm';
	} = $props();

	let open = $state(false);
	let popover: HTMLDivElement | undefined;
	let trigger: HTMLButtonElement | undefined;
	// Computed (top, left) for the popover when open. We render the popover
	// with `position: fixed` so it escapes any ancestor `overflow:hidden` —
	// the only way to ensure it's never clipped by a sticky filter bar or a
	// table cell with `truncate`.
	let popoverPos = $state<{ top: number; left: number } | null>(null);

	const copy = $derived(getMetric(metric, lang));
	const POPOVER_W = 360;

	function computePosition() {
		if (!trigger) return;
		const r = trigger.getBoundingClientRect();
		const margin = 8;
		const vw = window.innerWidth;
		const vh = window.innerHeight;
		// Prefer below-the-button. Flip above if there isn't enough room.
		const wantBelow = r.bottom + margin + 200 < vh || r.top - margin - 200 < 0;
		const top = wantBelow ? r.bottom + margin : Math.max(margin, r.top - margin - 240);
		// Left-anchor unless that would clip the right edge.
		let left = r.left;
		if (left + POPOVER_W + margin > vw) left = Math.max(margin, vw - POPOVER_W - margin);
		popoverPos = { top, left };
	}

	function toggle(e: MouseEvent) {
		e.stopPropagation();
		if (!open) computePosition();
		open = !open;
	}

	function close() {
		open = false;
		trigger?.focus();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && open) {
			e.preventDefault();
			close();
		}
	}

	function handleDocClick(e: MouseEvent) {
		if (!open) return;
		const t = e.target as Node;
		if (popover?.contains(t)) return;
		if (trigger?.contains(t)) return;
		open = false;
	}

	function handleReposition() {
		if (open) computePosition();
	}

	// $effect runs client-only and its cleanup callback handles both
	// dependency changes and unmount — so document/window references here
	// are always safe. The previous onDestroy block touched `document`
	// unconditionally and crashed SSR with "document is not defined".
	$effect(() => {
		if (!open) return;
		document.addEventListener('click', handleDocClick, true);
		document.addEventListener('keydown', handleKeydown);
		window.addEventListener('scroll', handleReposition, true);
		window.addEventListener('resize', handleReposition);
		return () => {
			document.removeEventListener('click', handleDocClick, true);
			document.removeEventListener('keydown', handleKeydown);
			window.removeEventListener('scroll', handleReposition, true);
			window.removeEventListener('resize', handleReposition);
		};
	});

	const btnSize = $derived(size === 'xs' ? 'h-3.5 w-3.5 text-[9px]' : 'h-4 w-4 text-[10px]');
</script>

<span class="relative inline-block align-middle">
	<button
		type="button"
		bind:this={trigger}
		onclick={toggle}
		aria-label={lang === 'zh' ? '查看说明' : 'What is this?'}
		aria-expanded={open}
		class="inline-grid {btnSize} place-items-center rounded-full border border-border bg-card text-muted-foreground transition-colors hover:border-primary hover:text-primary"
	>
		i
	</button>

	{#if open && copy && popoverPos}
		<div
			bind:this={popover}
			role="dialog"
			aria-modal="false"
			style="top: {popoverPos.top}px; left: {popoverPos.left}px;"
			class="fixed z-[1000] w-[320px] max-w-[calc(100vw-2rem)] rounded-lg border border-border bg-card p-3.5 text-left text-xs leading-relaxed shadow-2xl shadow-black/40 sm:w-[360px]"
		>
			<div class="mb-2 flex items-baseline justify-between gap-2">
				<h3 class="text-sm font-semibold text-foreground">{extraTitle ?? copy.name}</h3>
				<button
					type="button"
					onclick={close}
					aria-label={lang === 'zh' ? '关闭' : 'Close'}
					class="-mt-0.5 -mr-1 grid h-5 w-5 shrink-0 place-items-center rounded text-base text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
				>
					×
				</button>
			</div>

			<p class="mb-2 text-foreground">
				<span class="font-semibold text-muted-foreground">{lang === 'zh' ? '是什么' : 'What'}</span>
				· {copy.plain}
			</p>

			<p class="mb-2 text-foreground">
				<span class="font-semibold text-muted-foreground">{lang === 'zh' ? '为何重要' : 'Why'}</span
				>
				· {copy.why}
			</p>

			{#if note}
				<p class="mb-2 text-foreground">
					<span class="font-semibold text-muted-foreground"
						>{lang === 'zh' ? '怎么读这张图' : 'How to read'}</span
					>
					· {note}
				</p>
			{/if}

			{#if copy.rules && copy.rules.length > 0}
				<div class="mb-2">
					<div class="mb-1 font-semibold text-muted-foreground">
						{lang === 'zh' ? '经验阈值' : 'Rules of thumb'}
					</div>
					<ul class="ml-3 list-disc space-y-0.5 text-muted-foreground">
						{#each copy.rules as r, _i (_i)}
							<li>{r}</li>
						{/each}
					</ul>
				</div>
			{/if}

			{#if copy.formula}
				<div
					class="mt-2 rounded border border-dashed border-border bg-secondary/40 px-2 py-1 font-mono text-[10px] text-muted-foreground"
				>
					{copy.formula}
				</div>
			{/if}
		</div>
	{:else if open && popoverPos}
		<!-- Glossary entry missing — visible warning so the gap is obvious. -->
		<div
			bind:this={popover}
			role="dialog"
			style="top: {popoverPos.top}px; left: {popoverPos.left}px;"
			class="fixed z-[1000] w-[260px] rounded-lg border border-yellow-700/50 bg-yellow-950/40 p-3 text-xs text-yellow-200 shadow-2xl"
		>
			<p>{lang === 'zh' ? '说明缺失' : 'No glossary entry'}: <code>{metric}</code></p>
			{#if note}<p class="mt-1 text-yellow-100/80">{note}</p>{/if}
		</div>
	{/if}
</span>
