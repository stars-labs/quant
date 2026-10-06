<script lang="ts">
	import { t, type Lang } from '$lib/i18n';
	import { page } from '$app/stores';
	const lang = $derived<Lang>($page.data.lang ?? 'en');
	import { onMount } from 'svelte';
	import { getToken } from '$lib/auth';
	import { CONFIG } from '$lib/config';
	import { decisionText } from '$lib/runnerDecisions';
	import RunnerTelegram from '$lib/components/runner-telegram.svelte';
	import { execution, type RunnerConnection } from '$lib/execution';

	let connections = $state<RunnerConnection[]>([]);
	let signedIn = $state(false);
	let loading = $state(true);
	let busy = $state(false);
	let error = $state('');
	let label = $state('My HTX account');
	let labelEdited = $state(false);
	$effect(() => {
		if (!labelEdited) label = lang === 'zh' ? '我的 HTX 账户' : 'My HTX account';
	});
	let environment = $state<'dry_run' | 'live'>('dry_run');
	let displayConfig = $state('');
	let now = $state(Date.now());
	const active = $derived(connections.filter((connection) => !connection.revoked_at));
	const money = (value: number) =>
		new Intl.NumberFormat(lang === 'zh' ? 'zh-CN' : 'en-US', {
			style: 'currency',
			currency: 'USD'
		}).format(value);
	const quantity = (value: number) =>
		new Intl.NumberFormat(lang === 'zh' ? 'zh-CN' : 'en-US', {
			maximumSignificantDigits: 10
		}).format(value);
	const time = (value: string) => new Date(value).toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US');
	const fresh = (connection: RunnerConnection) =>
		!!connection.report &&
		!!connection.received_at &&
		now - Date.parse(connection.report.observed_at) < 5 * 60_000 &&
		now - Date.parse(connection.received_at) < 5 * 60_000;

	async function refresh() {
		signedIn = !!getToken();
		if (!signedIn) {
			connections = [];
			displayConfig = '';
			error = '';
			loading = false;
			return;
		}
		try {
			connections = await execution.connections();
			error = '';
		} catch {
			error = t(lang, 'web.account_displays_are_temporarily_unavailable');
		} finally {
			loading = false;
		}
	}

	async function create(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		error = '';
		try {
			const connection = await execution.create(label.trim(), environment);
			displayConfig = JSON.stringify(
				{ api_base: CONFIG.API_BASE, upload_token: connection.upload_token },
				null,
				2
			);
			await refresh();
		} catch {
			error = t(lang, 'web.could_not_create_the_display_connection');
		} finally {
			busy = false;
		}
	}

	function download() {
		const url = URL.createObjectURL(new Blob([displayConfig], { type: 'application/json' }));
		const link = document.createElement('a');
		link.href = url;
		link.download = 'display.json';
		link.click();
		URL.revokeObjectURL(url);
	}

	async function revoke(id: string) {
		busy = true;
		try {
			await execution.revoke(id);
			await refresh();
		} catch {
			error = t(lang, 'web.could_not_disconnect_reporting');
		} finally {
			busy = false;
		}
	}

	onMount(() => {
		void refresh();
		const timer = setInterval(() => {
			now = Date.now();
			void refresh();
		}, 30_000);
		return () => clearInterval(timer);
	});
</script>

<svelte:head>
	<title>{t(lang, 'web.your_accounts_starslab')}</title>
	<meta
		name="description"
		content={t(
			lang,
			'web.private_displays_for_trading_runners_on_your_own_computer_or_server_your_exchange_keys_sta'
		)}
	/>
	<meta name="robots" content="noindex" />
</svelte:head>

<main class="mx-auto w-full max-w-6xl min-w-0 px-4 py-8 sm:px-6">
	<header class="mb-8 max-w-3xl">
		<p class="mb-2 text-sm font-medium text-muted-foreground">
			{t(lang, 'web.your_machine_your_keys')}
		</p>
		<h1 class="text-3xl font-semibold tracking-tight">{t(lang, 'web.your_accounts')}</h1>
		<p class="mt-3 text-muted-foreground">
			{t(
				lang,
				'web.run_the_open_source_executor_on_your_computer_or_server_starslab_displays_the_account_data'
			)}
		</p>
		{#if signedIn}
			<button
				onclick={refresh}
				disabled={busy}
				class="mt-4 rounded-lg border border-border px-4 py-2 text-sm disabled:opacity-50"
				>{t(lang, 'web.refresh_account_displays')}</button
			>
		{/if}
	</header>

	<section class="mb-8 grid gap-4 sm:grid-cols-3" aria-label={t(lang, 'web.how_connection_works')}>
		{#each [['1', t(lang, 'web.install_your_runner'), t(lang, 'web.use_a_dedicated_spot_account_configure_exchange_permissions_and_trading_limits_locally')], ['2', t(lang, 'web.connect_the_display'), t(lang, 'web.download_a_reporting_configuration_here_it_contains_an_upload_token_never_an_exchange_key')], ['3', t(lang, 'web.review_your_account'), t(lang, 'web.see_positions_actual_fees_and_recent_fills_start_and_stop_trading_on_your_own_machine')]] as step (step[0])}
			<div class="rounded-xl border border-border bg-card p-5">
				<p class="text-sm text-muted-foreground">{t(lang, 'web.step')} {step[0]}</p>
				<h2 class="mt-2 font-semibold">{step[1]}</h2>
				<p class="mt-2 text-sm text-muted-foreground">{step[2]}</p>
			</div>
		{/each}
	</section>

	<p class="mb-6 text-sm">
		<a
			class="underline underline-offset-4"
			href="https://github.com/stars-labs/quant/tree/main/runner"
			target="_blank"
			rel="noreferrer">{t(lang, 'web.open_source_runner_and_setup_guide')}</a
		>
	</p>
	{#if error}<p
			role="alert"
			class="mb-6 rounded-lg border border-red-500/30 p-4 text-sm text-red-500"
		>
			{error}
		</p>{/if}
	{#if loading}
		<p aria-live="polite" class="py-8 text-muted-foreground">
			{t(lang, 'web.loading_your_account_displays')}
		</p>
	{:else if !signedIn}
		<section class="rounded-xl border border-border bg-card p-6">
			<h2 class="text-lg font-semibold">{t(lang, 'web.a_private_view_of_your_account')}</h2>
			<p class="mt-2 text-sm text-muted-foreground">
				{t(
					lang,
					'web.sign_in_to_create_a_display_connection_account_reports_are_visible_only_to_you'
				)}
			</p>
			<a
				href="/login?next=%2Fexecution"
				class="mt-4 inline-block rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
				>{t(lang, 'web.sign_in')}</a
			>
		</section>
	{:else}
		<section class="mb-8 rounded-xl border border-border bg-card p-6">
			<h2 class="text-lg font-semibold">{t(lang, 'web.connect_your_htx_runner')}</h2>
			<p class="mt-2 text-sm text-muted-foreground">
				{t(
					lang,
					'web.choose_the_report_type_to_match_your_local_runner_this_does_not_enable_trading'
				)}
			</p>
			{#if displayConfig}
				<div class="mt-5 rounded-lg border border-border p-4">
					<h3 class="font-medium">{t(lang, 'web.save_your_reporting_configuration')}</h3>
					<p class="mt-2 text-sm text-muted-foreground">
						{t(
							lang,
							'web.the_upload_token_is_shown_once_keep_the_file_on_your_runner_s_machine_it_permits_uploads_t'
						)}
					</p>
					<div class="mt-4 flex flex-wrap gap-3">
						<button
							onclick={download}
							class="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground"
							>{t(lang, 'web.save_display_json')}</button
						>
						<button
							onclick={() => (displayConfig = '')}
							class="rounded-lg border border-border px-4 py-2 text-sm"
							>{t(lang, 'web.i_saved_the_file')}</button
						>
					</div>
				</div>
			{:else}
				<form onsubmit={create} class="mt-5 flex flex-wrap items-end gap-4">
					<label class="grid gap-2 text-sm"
						>{t(lang, 'web.account_label')}<input
							bind:value={label}
							oninput={() => {
								labelEdited = true;
							}}
							required
							maxlength="64"
							class="rounded-lg border border-border bg-background px-3 py-2"
						/></label
					>
					<label class="grid gap-2 text-sm"
						>{t(lang, 'web.report_type')}<select
							bind:value={environment}
							class="rounded-lg border border-border bg-background px-3 py-2"
							><option value="dry_run">{t(lang, 'web.simulation')}</option><option value="live"
								>{t(lang, 'web.live_spot_account')}</option
							></select
						></label
					>
					<button
						disabled={busy || active.length >= 5}
						class="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
						>{busy ? t(lang, 'web.creating') : t(lang, 'web.create_display_connection')}</button
					>
				</form>
			{/if}
		</section>

		{#if active.length === 0}<p class="mb-8 text-muted-foreground">
				{t(
					lang,
					'web.no_accounts_connected_yet_your_first_report_will_appear_here_after_your_local_runner_start'
				)}
			</p>{/if}
		<RunnerTelegram {lang} />
		{#each active as connection (connection.id)}
			<section class="mb-8 rounded-xl border border-border bg-card p-5 sm:p-6">
				<div class="flex flex-wrap items-start justify-between gap-4">
					<div>
						<h2 class="text-xl font-semibold">{connection.label}</h2>
						<p class="mt-1 text-sm text-muted-foreground">
							{connection.venue.toUpperCase()} · {connection.environment === 'live'
								? t(lang, 'web.live_spot')
								: t(lang, 'web.simulation')}
							{t(lang, 'web.user_reported_data')}
						</p>
					</div>
					<span class="rounded-full border border-border px-3 py-1 text-xs"
						>{!connection.report
							? t(lang, 'web.waiting_for_first_report')
							: !fresh(connection)
								? t(lang, 'web.report_is_stale')
								: connection.report.status === 'healthy'
									? t(lang, 'web.reporting')
									: (lang === 'zh' ? '执行器：' : 'Runner ') +
										({
											paused: lang === 'zh' ? '暂停' : 'paused',
											pending: lang === 'zh' ? '订单待确认' : 'pending',
											stale: lang === 'zh' ? '数据过期' : 'stale'
										}[connection.report.status] ?? connection.report.status)}</span
					>
				</div>
				{#if connection.report}
					<p class="mt-3 text-xs text-muted-foreground">
						{t(lang, 'web.observed')}
						{time(connection.report.observed_at)}{t(
							lang,
							'web.valuation_uses_hourly_research_closes_these_figures_are_supplied_by_your_runner_and_are_no'
						)}
					</p>
					<div class="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
						{#each [[t(lang, 'web.tracked_equity'), connection.report.equity_usdt], [t(lang, 'web.tracked_cash'), connection.report.cash_usdt], [t(lang, 'web.confirmed_funding'), connection.report.funded_usdt], [connection.environment === 'live' ? t(lang, 'web.actual_fees') : t(lang, 'web.simulated_fees'), connection.report.fees_usdt]] as metric (metric[0])}
							<div>
								<p class="text-xs text-muted-foreground">{metric[0]}</p>
								<p class="mt-1 text-xl font-semibold">{money(Number(metric[1]))}</p>
							</div>
						{/each}
					</div>
					<p class="mt-4 text-sm text-muted-foreground">
						{t(lang, 'web.estimated_net_p_l')}
						{money(connection.report.equity_usdt - connection.report.funded_usdt)}
						{t(lang, 'web.available_trend_budget')}
						{money(connection.report.trend_available_usdt)}
						{t(lang, 'web.current_month_dca')}
						{money(connection.report.dca_available_usdt)}
					</p>
					{#if connection.report.decisions?.length}
						<h3 class="mt-6 font-medium">
							{lang === 'zh' ? '最近一轮执行说明' : 'Latest execution decisions'}
						</h3>
						<ul class="mt-2 space-y-1 text-sm text-muted-foreground">
							{#each connection.report.decisions as decision, index (index)}
								<li>
									{decision.asset ?? (lang === 'zh' ? '账户' : 'Account')} · {decision.strategy ===
									'trend'
										? lang === 'zh'
											? '趋势'
											: 'Trend'
										: decision.strategy === 'dca'
											? lang === 'zh'
												? '定投'
												: 'DCA'
											: ''} · {decisionText(decision.reason, lang)}
								</li>
							{/each}
						</ul>
					{/if}
					{#if connection.report.history?.length}
						<h3 class="mt-6 font-medium">{lang === 'zh' ? '账户历史' : 'Account history'}</h3>
						<p class="mt-2 text-xs text-muted-foreground">
							{lang === 'zh'
								? '充值和提款不计入盈亏。按小时保留最新观测，估值使用研究收盘价。'
								: 'Deposits and withdrawals are excluded from PnL. Latest observation per hour; valuations use research closes.'}
						</p>
						<div class="mt-3 overflow-x-auto">
							<table class="w-full text-left text-sm">
								<thead
									><tr
										><th class="py-2 pr-4">{lang === 'zh' ? '观测时间' : 'Observed'}</th><th
											class="pr-4">{lang === 'zh' ? '估值时间' : 'Price time'}</th
										><th class="pr-4">{lang === 'zh' ? '权益' : 'Equity'}</th><th class="pr-4"
											>{lang === 'zh' ? '净投入' : 'Net contributions'}</th
										><th>{lang === 'zh' ? '估计盈亏' : 'Estimated PnL'}</th></tr
									></thead
								>
								<tbody
									>{#each [...connection.report.history].reverse() as point (point.observed_at)}<tr
											class="border-t border-border"
											><td class="py-2 pr-4 whitespace-nowrap">{time(point.observed_at)}</td><td
												class="pr-4 whitespace-nowrap">{time(point.price_as_of)}</td
											><td class="pr-4">{money(point.equity_usdt)}</td><td class="pr-4"
												>{money(point.net_contributions_usdt)}</td
											><td>{money(point.net_pnl_usdt)}</td></tr
										>{/each}</tbody
								>
							</table>
						</div>
					{/if}
					<h3 class="mt-6 font-medium">{t(lang, 'web.positions')}</h3>
					{#if connection.report.positions.length === 0}<p
							class="mt-2 text-sm text-muted-foreground"
						>
							{t(lang, 'web.no_open_positions')}
						</p>{:else}
						<div class="mt-3 overflow-x-auto">
							<table class="w-full text-left text-sm">
								<thead
									><tr class="border-b border-border text-xs text-muted-foreground"
										><th class="py-2 pr-4">{t(lang, 'web.asset')}</th><th class="pr-4"
											>{t(lang, 'web.strategy')}</th
										><th class="pr-4">{t(lang, 'web.quantity')}</th><th class="pr-4"
											>{t(lang, 'web.value')}</th
										><th>{t(lang, 'web.realized_p_l')}</th></tr
									></thead
								><tbody
									>{#each connection.report.positions as position, index (index)}<tr
											class="border-b border-border/50"
											><td class="py-3 pr-4 font-medium">{position.asset}</td><td class="pr-4"
												>{position.strategy === 'dca'
													? t(lang, 'web.btc_dca')
													: t(lang, 'web.trend')}</td
											><td class="pr-4">{quantity(position.quantity)}</td><td class="pr-4"
												>{money(position.quantity * position.price_usdt)}</td
											><td>{money(position.realized_pnl_usdt)}</td></tr
										>{/each}</tbody
								>
							</table>
						</div>
					{/if}
					<h3 class="mt-6 font-medium">{t(lang, 'web.recent_fills')}</h3>
					{#if connection.report.fills.length === 0}<p class="mt-2 text-sm text-muted-foreground">
							{t(lang, 'web.no_fills_reported_yet')}
						</p>{:else}
						<div class="mt-3 overflow-x-auto">
							<table class="w-full text-left text-sm">
								<thead
									><tr class="border-b border-border text-xs text-muted-foreground"
										><th class="py-2 pr-4">{t(lang, 'web.time')}</th><th class="pr-4"
											>{t(lang, 'web.trade')}</th
										><th class="pr-4">{t(lang, 'web.quantity')}</th><th class="pr-4"
											>{t(lang, 'web.quote_value')}</th
										><th>{t(lang, 'web.fee')}</th></tr
									></thead
								><tbody
									>{#each connection.report.fills as fill, index (index)}<tr
											class="border-b border-border/50"
											><td class="py-3 pr-4 whitespace-nowrap">{time(fill.finished_at)}</td><td
												class="pr-4 whitespace-nowrap"
												>{fill.side === 'buy' ? t(lang, 'web.buy') : t(lang, 'web.sell')}
												{fill.asset}</td
											><td class="pr-4">{quantity(fill.quantity)}</td><td class="pr-4"
												>{money(fill.quote_usdt)}</td
											><td class="whitespace-nowrap"
												>{money(fill.fee_usdt)} · {(fill.fee_rate * 100).toFixed(3)}%</td
											></tr
										>{/each}</tbody
								>
							</table>
						</div>
					{/if}
				{/if}
				<footer class="mt-6 border-t border-border pt-4">
					<button
						disabled={busy}
						onclick={() => revoke(connection.id)}
						class="text-sm underline underline-offset-4 disabled:opacity-50"
						>{t(lang, 'web.disconnect_reporting')}</button
					>
					<p class="mt-2 text-xs text-muted-foreground">
						{t(
							lang,
							'web.disconnecting_stops_uploads_only_stop_trading_on_the_computer_or_server_running_your_execu'
						)}
					</p>
				</footer>
			</section>
		{/each}
	{/if}
</main>
