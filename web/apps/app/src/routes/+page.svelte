<script lang="ts">
	import { t, type Lang } from '$lib/i18n';
	import type { PageData } from './$types';
	import { invalidateAll } from '$app/navigation';
	import { ArrowRight, BookOpen, FlaskConical, Wallet, Radio, ExternalLink } from 'lucide-svelte';
	let { data }: { data: PageData } = $props();
	const lang = $derived<Lang>(data.lang ?? 'en');
	const overview = $derived(data.overview);
	let refreshing = $state(false);
	let refreshError = $state(false);
	async function refresh() {
		refreshing = true;
		refreshError = false;
		try {
			await invalidateAll();
		} catch {
			refreshError = true;
		} finally {
			refreshing = false;
		}
	}
	const paths = $derived([
		{
			title: t(lang, 'web.understand_the_strategy'),
			text: t(
				lang,
				'web.review_the_house_rules_recorded_signals_losses_and_historical_comparisons'
			),
			href: '/record',
			action: t(lang, 'web.explore_the_track_record'),
			icon: BookOpen
		},
		{
			title: t(lang, 'web.test_your_own_ideas'),
			text: t(
				lang,
				'web.explore_historical_backtests_and_inspect_assumptions_before_drawing_conclusions'
			),
			href: '/backtest',
			action: t(lang, 'web.open_the_research_playground'),
			icon: FlaskConical
		},
		{
			title: t(lang, 'web.connect_your_own_account'),
			text: t(
				lang,
				'web.run_the_open_source_htx_executor_on_your_device_and_keep_a_private_view_of_its_reports'
			),
			href: '/execution',
			action: t(lang, 'web.set_up_your_account_display'),
			icon: Wallet
		}
	]);
	function percent(value: number) {
		return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
	}
</script>

<svelte:head>
	<title>{t(lang, 'web.research_signals_trade_on_your_terms_starslab')}</title>
	<meta
		name="description"
		content={t(
			lang,
			'web.explore_transparent_strategy_research_review_recorded_signals_and_connect_an_owner_operate'
		)}
	/>
	<meta
		property="og:title"
		content={t(lang, 'web.research_signals_trade_on_your_terms_starslab')}
	/>
	<meta
		property="og:description"
		content={t(
			lang,
			'web.public_research_visible_assumptions_and_private_account_reports_execution_stays_on_your_co'
		)}
	/>
</svelte:head>

<main class="mx-auto w-full max-w-6xl min-w-0 px-4 py-10 sm:px-8">
	<section
		class="rounded-2xl border border-border bg-gradient-to-br from-primary/10 via-card to-card p-6 sm:p-10"
	>
		<p class="text-xs font-medium tracking-widest text-primary uppercase">
			{t(lang, 'web.open_research_owner_operated_execution')}
		</p>
		<h1 class="mt-4 max-w-3xl text-3xl leading-tight font-semibold tracking-tight sm:text-5xl">
			{t(lang, 'web.understand_the_rules')}<br />{t(lang, 'web.trade_on_your_terms')}
		</h1>
		<p class="mt-5 max-w-2xl text-base leading-relaxed text-muted-foreground">
			{t(
				lang,
				'web.explore_the_evidence_behind_a_strategy_test_your_own_ideas_and_review_your_account_in_one_'
			)}
		</p>
		<div class="mt-7 flex flex-wrap gap-3">
			<a
				href="/record"
				class="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-3 font-medium text-primary-foreground"
				>{t(lang, 'web.review_the_track_record')} <ArrowRight size={16} /></a
			>
			<a
				href="/execution"
				class="inline-flex items-center gap-2 rounded-lg border border-border bg-background px-5 py-3 font-medium"
				>{t(lang, 'web.connect_your_runner')} <Wallet size={16} /></a
			>
		</div>
		<a
			href="/start"
			class="mt-5 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
			>{t(lang, 'web.new_here_start_with_the_three_minute_guide')} <ArrowRight size={14} /></a
		>
	</section>

	<section class="mt-10" aria-labelledby="paths-title">
		<h2 id="paths-title" class="text-xl font-semibold">{t(lang, 'web.choose_your_next_step')}</h2>
		<div class="mt-4 grid gap-4 lg:grid-cols-3">
			{#each paths as path (path.href)}
				<a
					href={path.href}
					class="flex flex-col rounded-xl border border-border bg-card p-5 transition-colors hover:border-primary focus-visible:ring-2 focus-visible:ring-primary"
				>
					<path.icon size={22} class="text-primary" />
					<h3 class="mt-4 font-semibold">{path.title}</h3>
					<p class="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">{path.text}</p>
					<span class="mt-5 inline-flex items-center gap-1 text-sm font-medium text-primary"
						>{path.action} <ArrowRight size={14} /></span
					>
				</a>
			{/each}
		</div>
	</section>

	<section
		class="mt-10 rounded-xl border border-border bg-card p-5 sm:p-7"
		aria-labelledby="snapshot-title"
	>
		<div class="flex flex-wrap items-center justify-between gap-3">
			<div>
				<p class="text-xs tracking-wide text-muted-foreground uppercase">
					{t(lang, 'web.public_research_hourly_donchian_rule')}
				</p>
				<h2 id="snapshot-title" class="mt-1 text-xl font-semibold">
					{t(lang, 'web.the_current_house_rule_snapshot')}
				</h2>
			</div>
			<div class="flex flex-wrap items-center gap-3">
				<button
					type="button"
					onclick={refresh}
					disabled={refreshing}
					class="rounded-lg border px-3 py-2 text-xs hover:bg-accent disabled:opacity-50"
					>{refreshing ? t(lang, 'web.refreshing') : t(lang, 'web.refresh_data')}</button
				>
				<span class="rounded-full border px-3 py-1 text-xs"
					>{!overview
						? t(lang, 'web.data_unavailable')
						: overview.stale
							? t(lang, 'web.update_delayed')
							: t(lang, 'web.hourly_data')}</span
				>
			</div>
		</div>
		{#if refreshError}<p role="status" class="mt-3 text-sm text-muted-foreground">
				{t(
					lang,
					'web.could_not_refresh_the_previous_snapshot_remains_visible_check_its_timestamp_before_using_i'
				)}
			</p>{/if}
		{#if overview}
			<p class="mt-3 text-xs text-muted-foreground">
				{t(lang, 'web.oldest_asset_close')}
				{overview.asOf.replace('T', ' ').slice(0, 16)}
				{t(lang, 'web.utc_historical_baseline')}
				{overview.start.slice(0, 10)}.
			</p>
			{#if overview.stale}<p
					role="status"
					class="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm"
				>
					{t(
						lang,
						'web.some_prices_are_over_three_hours_old_the_figures_below_are_historical_not_a_current_tradin'
					)}
				</p>{/if}
			<div class="mt-5 grid grid-cols-2 gap-4 lg:grid-cols-4">
				{#each [[t(lang, 'web.research_assets'), overview.assets.length], [t(lang, 'web.open_rule_signals'), overview.open], [t(lang, 'web.closed_rule_trades'), overview.closed], [t(lang, 'web.model_return'), percent(overview.modelReturn)]] as item (item[0])}
					<div class="min-w-0 rounded-lg bg-secondary/40 p-4">
						<p class="text-xs text-muted-foreground">{item[0]}</p>
						<p class="mt-2 text-2xl font-semibold tabular-nums">{item[1]}</p>
					</div>
				{/each}
			</div>
			<p class="mt-4 text-sm text-muted-foreground">
				{t(lang, 'web.equal_weight_buy_and_hold_comparison')}
				{percent(overview.holdReturn)}
				{t(lang, 'web.over_the_same_history')}
			</p>
			<p class="mt-2 text-xs leading-relaxed text-muted-foreground">
				{t(
					lang,
					'web.the_model_includes_reconstructed_history_and_assumes_0_1_fees_per_side_these_are_rule_base'
				)}
			</p>
		{:else}
			<p role="status" class="mt-5 text-sm text-muted-foreground">
				{t(
					lang,
					'web.the_research_snapshot_could_not_be_loaded_missing_data_is_not_shown_as_zero_returns_or_no_'
				)}
			</p>
		{/if}
		<div class="mt-5 flex flex-wrap gap-5 text-sm">
			<a href="/record" class="text-primary hover:underline"
				>{t(lang, 'web.full_history_and_live_recording_split')}</a
			><a href="/method" class="text-primary hover:underline"
				>{t(lang, 'web.rules_assumptions_and_costs')}</a
			>
		</div>
	</section>

	<section class="mt-10 grid gap-4 md:grid-cols-2">
		<div class="rounded-xl border border-border bg-card p-6">
			<Radio size={22} class="text-primary" />
			<h2 class="mt-3 text-lg font-semibold">{t(lang, 'web.observe_the_market')}</h2>
			<p class="mt-2 text-sm leading-relaxed text-muted-foreground">
				{data.market
					? `${lang === 'zh' ? '综合市场压力：' : 'Composite market stress: '}${data.market.score.toFixed(0)}/100${data.market.stale ? t(lang, 'web.delayed_reading') : ''}.`
					: t(lang, 'web.the_market_stress_reading_is_currently_unavailable')}
				{t(lang, 'web.these_observations_provide_context_they_do_not_place_trades')}
			</p>
			{#if data.market}<p class="mt-2 text-xs text-muted-foreground">
					{t(lang, 'web.updated')}
					{data.market.asOf.replace('T', ' ').slice(0, 16)} UTC.
				</p>{/if}
			<div class="mt-5 flex flex-wrap gap-4 text-sm">
				<a href="/market" class="text-primary hover:underline">{t(lang, 'web.market_context')}</a>
				<a href="/scan" class="text-primary hover:underline">{t(lang, 'web.opportunity_radar')}</a
				><a href="/semis" class="text-primary hover:underline"
					>{t(lang, 'web.semiconductor_research')}</a
				>
			</div>
		</div>
		<div class="rounded-xl border border-border bg-card p-6">
			<Wallet size={22} class="text-primary" />
			<h2 class="mt-3 text-lg font-semibold">
				{t(lang, 'web.a_private_view_not_a_managed_account')}
			</h2>
			<p class="mt-2 text-sm leading-relaxed text-muted-foreground">
				{t(
					lang,
					'web.connect_an_upload_only_display_token_to_review_positions_actual_fees_and_recent_fills_star'
				)}
			</p>
			<a
				href="https://github.com/stars-labs/quant/tree/main/runner"
				target="_blank"
				rel="noopener noreferrer"
				class="mt-5 inline-flex items-center gap-1 text-sm text-primary hover:underline"
				>{t(lang, 'web.read_the_open_source_setup_guide')} <ExternalLink size={14} /></a
			>
		</div>
	</section>
	<p class="mt-8 text-xs leading-relaxed text-muted-foreground">
		{t(
			lang,
			'web.historical_research_can_lose_money_and_does_not_predict_future_returns_public_testnet_and_'
		)}
	</p>
</main>
