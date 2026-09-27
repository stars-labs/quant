<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { session } from '$lib/auth';
	import { loadPrefs } from '$lib/userPrefs';
	import { simulateDca, type OhlcByCoin } from '$lib/dcaSim';
	import { fmtUSD, fmtPct } from '$lib/utils';
	import { t, type Lang } from '$lib/i18n';

	// Home-page personal greeting. Empty state (nothing rendered) if not
	// logged in — the rest of the home page covers the anon case.
	let { ohlcByCoin }: { ohlcByCoin: OhlcByCoin } = $props();

	const lang = $derived<Lang>($page.data.lang ?? 'zh');
	const name = $derived(
		($session?.user?.email ?? '').split('@')[0] || ($session?.user?.sub ?? '').slice(0, 6)
	);

	let loaded = $state(false);
	let summary = $state<{ invested: number; value: number; roi: number } | null>(null);

	onMount(async () => {
		if (!$session) {
			loaded = true;
			return;
		}
		try {
			const p = await loadPrefs(fetch);
			if (p?.dca_plan) {
				const r = simulateDca(p.dca_plan, ohlcByCoin);
				summary = {
					invested: r.summary.total_invested,
					value: r.summary.current_value,
					roi: r.summary.roi_pct
				};
			}
		} catch {
			// non-fatal — just hide the banner
		} finally {
			loaded = true;
		}
	});
</script>

{#if $session && loaded}
	<div
		class="relative mb-6 overflow-hidden rounded-lg border border-[var(--dawn-glow)] bg-card p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]"
	>
		<!-- Dawn radial glows: warm coral bottom-left, cosmic violet top-right -->
		<div
			class="pointer-events-none absolute inset-0"
			style="background:
				radial-gradient(ellipse 60% 100% at 0% 100%, rgba(255,138,92,0.18) 0%, transparent 60%),
				radial-gradient(ellipse 50% 80% at 100% 0%, rgba(124,92,255,0.12) 0%, transparent 60%);"
		></div>
		<div class="relative flex flex-wrap items-center justify-between gap-4">
			<div class="min-w-0">
				<div class="bdv-eyebrow text-[var(--gold-500)]">{t(lang, 'plan.greeting')}</div>
				<div class="bdv-display mt-1.5 text-[22px] leading-none font-semibold tracking-[-0.01em]">
					{name}
				</div>
			</div>
			{#if summary && summary.invested > 0}
				<div class="flex flex-wrap items-baseline gap-5">
					<div>
						<div class="bdv-eyebrow">{t(lang, 'plan.result.invested')}</div>
						<div class="bdv-num mt-1 text-[18px] font-bold tracking-[-0.02em]">
							{fmtUSD(summary.invested)}
						</div>
					</div>
					<div class="bdv-num text-muted-foreground">→</div>
					<div>
						<div class="bdv-eyebrow">{t(lang, 'plan.result.value')}</div>
						<div class="bdv-num mt-1 text-[18px] font-bold tracking-[-0.02em]">
							{fmtUSD(summary.value)}
						</div>
					</div>
					<div>
						<div class="bdv-eyebrow">{t(lang, 'plan.result.roi')}</div>
						<div
							class="bdv-num mt-1 text-[18px] font-bold tracking-[-0.02em]"
							class:text-[var(--profit)]={summary.roi > 0}
							class:text-[var(--loss)]={summary.roi < 0}
						>
							{fmtPct(summary.roi)}
						</div>
					</div>
					<a
						href="/dca"
						class="bdv-num text-[11px] tracking-[0.12em] text-[var(--dawn-500)] uppercase transition-colors hover:text-[var(--dawn-300)]"
						>→ /dca</a
					>
				</div>
			{:else}
				<a
					href="/dca"
					class="text-sm text-[var(--dawn-500)] transition-colors hover:text-[var(--dawn-300)]"
				>
					{t(lang, 'plan.greetingNoPlan')}
				</a>
			{/if}
		</div>
	</div>
{/if}
