<script lang="ts">
	import { t, type Lang } from '$lib/i18n';
	import { page } from '$app/stores';
	const lang = $derived<Lang>($page.data.lang ?? 'en');
	import { BookOpen, FlaskConical, Wallet, ArrowRight, ExternalLink } from 'lucide-svelte';
	const steps = $derived([
		{
			title: t(lang, 'web.read_the_evidence'),
			text: t(
				lang,
				'web.start_with_the_public_house_rule_record_compare_the_strategy_with_buy_and_hold_check_the_h'
			),
			href: '/record',
			action: t(lang, 'web.explore_the_track_record'),
			icon: BookOpen
		},
		{
			title: t(lang, 'web.explore_before_committing'),
			text: t(
				lang,
				'web.use_the_backtest_playground_to_inspect_a_strategy_testnet_and_paper_fills_demonstrate_exec'
			),
			href: '/backtest',
			action: t(lang, 'web.try_the_research_playground'),
			icon: FlaskConical
		},
		{
			title: t(lang, 'web.run_on_your_own_device'),
			text: t(
				lang,
				'web.if_you_choose_live_execution_install_the_open_source_htx_runner_on_your_computer_or_server'
			),
			href: '/execution',
			action: t(lang, 'web.connect_a_private_account_display'),
			icon: Wallet
		}
	]);
	const questions = $derived([
		{
			title: t(lang, 'web.is_the_public_track_record_my_actual_return'),
			answer: t(
				lang,
				'web.no_it_models_the_published_rule_includes_reconstructed_history_and_assumes_0_1_fees_per_si'
			)
		},
		{
			title: t(lang, 'web.does_connecting_a_display_start_trading'),
			answer: t(
				lang,
				'web.no_the_downloaded_configuration_contains_an_upload_only_token_it_lets_your_local_runner_se'
			)
		},
		{
			title: t(lang, 'web.where_do_i_put_my_exchange_keys'),
			answer: t(
				lang,
				'web.only_on_the_computer_or_server_running_your_executor_use_a_dedicated_spot_account_with_rea'
			)
		},
		{
			title: t(lang, 'web.how_do_monthly_budgets_work'),
			answer: t(
				lang,
				'web.choose_limits_locally_and_confirm_deposited_funding_with_the_runner_a_new_calendar_month_d'
			)
		},
		{
			title: t(lang, 'web.how_do_i_stop_trading'),
			answer: t(
				lang,
				'web.stop_the_executor_on_your_own_computer_or_server_disconnecting_the_display_only_stops_repo'
			)
		},
		{
			title: t(lang, 'web.what_does_an_old_or_missing_report_mean'),
			answer: t(
				lang,
				'web.it_means_the_website_has_no_recent_update_the_local_executor_may_still_be_running_check_th'
			)
		},
		{
			title: t(lang, 'web.which_exchanges_are_supported'),
			answer: t(
				lang,
				'web.the_public_runner_currently_supports_htx_spot_live_execution_and_simulation_gate_live_exec'
			)
		},
		{
			title: t(lang, 'web.are_fees_and_risk_hidden'),
			answer: t(
				lang,
				'web.private_runner_reports_use_reconciled_fill_fees_including_base_asset_deductions_account_va'
			)
		}
	]);
</script>

<svelte:head>
	<title>{t(lang, 'web.getting_started_starslab')}</title>
	<meta
		name="description"
		content={t(
			lang,
			'web.understand_starslab_research_test_strategies_and_connect_a_private_owner_operated_htx_runn'
		)}
	/>
	<meta property="og:title" content={t(lang, 'web.getting_started_starslab')} />
	<meta
		property="og:description"
		content={t(lang, 'web.research_first_execute_on_your_device_keep_your_account_reports_private')}
	/>
</svelte:head>

<main class="mx-auto w-full max-w-4xl min-w-0 px-5 py-10 sm:px-8">
	<p class="text-xs tracking-wide text-primary uppercase">{t(lang, 'web.getting_started')}</p>
	<h1 class="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
		{t(lang, 'web.a_clear_path_from_research_to_your_own_account')}
	</h1>
	<p class="mt-4 max-w-3xl leading-relaxed text-muted-foreground">
		{t(
			lang,
			'web.starslab_publishes_research_and_displays_account_reports_you_decide_what_to_run_the_live_e'
		)}
	</p>
	<div class="mt-8 grid gap-4 md:grid-cols-3">
		{#each steps as step, i (step.href)}
			<section class="flex flex-col rounded-xl border border-border bg-card p-5">
				<step.icon size={22} class="text-primary" />
				<p class="mt-4 text-xs text-muted-foreground">{t(lang, 'web.step')} {i + 1}</p>
				<h2 class="mt-1 text-lg font-semibold">{step.title}</h2>
				<p class="mt-3 flex-1 text-sm leading-relaxed text-muted-foreground">{step.text}</p>
				<a
					href={step.href}
					class="mt-5 inline-flex items-center gap-1 text-sm text-primary hover:underline"
					>{step.action} <ArrowRight size={14} /></a
				>
			</section>
		{/each}
	</div>

	<section class="mt-10 rounded-xl border border-border bg-card p-6" aria-labelledby="setup-title">
		<h2 id="setup-title" class="text-xl font-semibold">
			{t(lang, 'web.your_first_runner_connection')}
		</h2>
		<ol class="mt-4 list-decimal space-y-3 pl-5 text-sm leading-relaxed text-muted-foreground">
			<li>
				{t(
					lang,
					'web.install_the_open_source_runner_using_the_official_setup_guide_a_fresh_installation_starts_'
				)}
			</li>
			<li>
				{t(
					lang,
					'web.run_a_simulation_and_inspect_its_local_status_review_the_strategy_budget_limits_and_order_'
				)}
			</li>
			<li>
				{t(
					lang,
					'web.sign_in_to_your_accounts_choose_the_report_type_matching_your_local_runner_and_download_th'
				)}
			</li>
			<li>
				{t(
					lang,
					'web.attach_the_reporting_file_on_your_device_verify_that_the_account_display_receives_a_recent'
				)}
			</li>
			<li>
				{t(
					lang,
					'web.if_you_choose_live_trading_configure_and_authorize_it_locally_confirm_deposited_funding_an'
				)}
			</li>
		</ol>
		<div class="mt-6 flex flex-wrap gap-4 text-sm">
			<a href="/execution" class="inline-flex items-center gap-1 text-primary hover:underline"
				>{t(lang, 'web.open_your_accounts')} <ArrowRight size={14} /></a
			>
			<a
				href="https://github.com/stars-labs/quant/tree/main/runner"
				target="_blank"
				rel="noopener noreferrer"
				class="inline-flex items-center gap-1 text-primary hover:underline"
				>{t(lang, 'web.install_and_operate_the_runner')} <ExternalLink size={14} /></a
			>
		</div>
	</section>

	<section class="mt-10" aria-labelledby="faq-title">
		<h2 id="faq-title" class="text-xl font-semibold">
			{t(lang, 'web.questions_before_you_connect')}
		</h2>
		<div class="mt-4 space-y-3">
			{#each questions as question (question.title)}
				<details class="rounded-xl border border-border bg-card p-5">
					<summary class="cursor-pointer font-medium">{question.title}</summary>
					<p class="mt-3 text-sm leading-relaxed text-muted-foreground">{question.answer}</p>
				</details>
			{/each}
		</div>
	</section>
	<p class="mt-8 text-sm text-muted-foreground">
		{t(lang, 'web.want_to_understand_the_rule_before_using_it')}
		<a href="/method" class="text-primary hover:underline"
			>{t(lang, 'web.read_the_methodology_and_cost_assumptions')}</a
		>
	</p>
</main>
