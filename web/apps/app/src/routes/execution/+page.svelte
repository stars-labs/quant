<script lang="ts">
	import { onMount } from 'svelte';
	import { getToken } from '$lib/auth';
	import { CONFIG } from '$lib/config';
	import { execution, type RunnerConnection } from '$lib/execution';

	let connections = $state<RunnerConnection[]>([]);
	let signedIn = $state(false);
	let loading = $state(true);
	let busy = $state(false);
	let error = $state('');
	let label = $state('My HTX account');
	let environment = $state<'dry_run' | 'live'>('dry_run');
	let displayConfig = $state('');
	let now = $state(Date.now());
	const active = $derived(connections.filter((connection) => !connection.revoked_at));
	const money = (value: number) =>
		new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
	const quantity = (value: number) =>
		new Intl.NumberFormat('en-US', { maximumSignificantDigits: 10 }).format(value);
	const time = (value: string) => new Date(value).toLocaleString('en-US');
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
		} catch (cause) {
			error =
				cause instanceof Error ? cause.message : 'Account displays are temporarily unavailable.';
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
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not create the display connection.';
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
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not disconnect reporting.';
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
	<title>Your accounts · Starslab</title>
	<meta
		name="description"
		content="Private displays for trading runners on your own computer or server. Your exchange keys stay with you."
	/>
	<meta name="robots" content="noindex" />
</svelte:head>

<main class="mx-auto w-full max-w-6xl min-w-0 px-4 py-8 sm:px-6">
	<header class="mb-8 max-w-3xl">
		<p class="mb-2 text-sm font-medium text-muted-foreground">Your machine. Your keys.</p>
		<h1 class="text-3xl font-semibold tracking-tight">Your accounts</h1>
		<p class="mt-3 text-muted-foreground">
			Run the open-source executor on your computer or server. Starslab displays the account data
			your runner uploads. Trading and exchange credentials stay on your machine.
		</p>
		{#if signedIn}
			<button
				onclick={refresh}
				disabled={busy}
				class="mt-4 rounded-lg border border-border px-4 py-2 text-sm disabled:opacity-50"
				>Refresh account displays</button
			>
		{/if}
	</header>

	<section class="mb-8 grid gap-4 sm:grid-cols-3" aria-label="How connection works">
		{#each [['1', 'Install your runner', 'Use a dedicated spot account. Configure exchange permissions and trading limits locally.'], ['2', 'Connect the display', 'Download a reporting configuration here. It contains an upload token, never an exchange key.'], ['3', 'Review your account', 'See positions, actual fees and recent fills. Start and stop trading on your own machine.']] as step (step[0])}
			<div class="rounded-xl border border-border bg-card p-5">
				<p class="text-sm text-muted-foreground">Step {step[0]}</p>
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
			rel="noreferrer">Open-source runner and setup guide ↗</a
		>
	</p>
	{#if error}<p
			role="alert"
			class="mb-6 rounded-lg border border-red-500/30 p-4 text-sm text-red-500"
		>
			{error}
		</p>{/if}
	{#if loading}
		<p aria-live="polite" class="py-8 text-muted-foreground">Loading your account displays…</p>
	{:else if !signedIn}
		<section class="rounded-xl border border-border bg-card p-6">
			<h2 class="text-lg font-semibold">A private view of your account</h2>
			<p class="mt-2 text-sm text-muted-foreground">
				Sign in to create a display connection. Account reports are visible only to you.
			</p>
			<a
				href="/login?next=%2Fexecution"
				class="mt-4 inline-block rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
				>Sign in</a
			>
		</section>
	{:else}
		<section class="mb-8 rounded-xl border border-border bg-card p-6">
			<h2 class="text-lg font-semibold">Connect your HTX runner</h2>
			<p class="mt-2 text-sm text-muted-foreground">
				Choose the report type to match your local runner. This does not enable trading.
			</p>
			{#if displayConfig}
				<div class="mt-5 rounded-lg border border-border p-4">
					<h3 class="font-medium">Save your reporting configuration</h3>
					<p class="mt-2 text-sm text-muted-foreground">
						The upload token is shown once. Keep the file on your runner's machine. It permits
						uploads to this display only.
					</p>
					<div class="mt-4 flex flex-wrap gap-3">
						<button
							onclick={download}
							class="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground"
							>Save display.json</button
						>
						<button
							onclick={() => (displayConfig = '')}
							class="rounded-lg border border-border px-4 py-2 text-sm">I saved the file</button
						>
					</div>
				</div>
			{:else}
				<form onsubmit={create} class="mt-5 flex flex-wrap items-end gap-4">
					<label class="grid gap-2 text-sm"
						>Account label<input
							bind:value={label}
							required
							maxlength="64"
							class="rounded-lg border border-border bg-background px-3 py-2"
						/></label
					>
					<label class="grid gap-2 text-sm"
						>Report type<select
							bind:value={environment}
							class="rounded-lg border border-border bg-background px-3 py-2"
							><option value="dry_run">Simulation</option><option value="live"
								>Live spot account</option
							></select
						></label
					>
					<button
						disabled={busy || active.length >= 5}
						class="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
						>{busy ? 'Creating…' : 'Create display connection'}</button
					>
				</form>
			{/if}
		</section>

		{#if active.length === 0}<p class="mb-8 text-muted-foreground">
				No accounts connected yet. Your first report will appear here after your local runner starts
				uploading.
			</p>{/if}
		{#each active as connection (connection.id)}
			<section class="mb-8 rounded-xl border border-border bg-card p-5 sm:p-6">
				<div class="flex flex-wrap items-start justify-between gap-4">
					<div>
						<h2 class="text-xl font-semibold">{connection.label}</h2>
						<p class="mt-1 text-sm text-muted-foreground">
							{connection.venue.toUpperCase()} · {connection.environment === 'live'
								? 'Live spot'
								: 'Simulation'} · User-reported data
						</p>
					</div>
					<span class="rounded-full border border-border px-3 py-1 text-xs"
						>{!connection.report
							? 'Waiting for first report'
							: !fresh(connection)
								? 'Report is stale'
								: connection.report.status === 'healthy'
									? 'Reporting'
									: `Runner ${connection.report.status}`}</span
					>
				</div>
				{#if connection.report}
					<p class="mt-3 text-xs text-muted-foreground">
						Observed {time(connection.report.observed_at)}. Valuation uses hourly research closes.
						These figures are supplied by your runner and are not independently verified by
						Starslab.
					</p>
					<div class="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
						{#each [['Tracked equity', connection.report.equity_usdt], ['Tracked cash', connection.report.cash_usdt], ['Confirmed funding', connection.report.funded_usdt], [connection.environment === 'live' ? 'Actual fees' : 'Simulated fees', connection.report.fees_usdt]] as metric (metric[0])}
							<div>
								<p class="text-xs text-muted-foreground">{metric[0]}</p>
								<p class="mt-1 text-xl font-semibold">{money(Number(metric[1]))}</p>
							</div>
						{/each}
					</div>
					<p class="mt-4 text-sm text-muted-foreground">
						Estimated net P&amp;L {money(
							connection.report.equity_usdt - connection.report.funded_usdt
						)} · Available trend budget {money(connection.report.trend_available_usdt)} · Current-month
						DCA
						{money(connection.report.dca_available_usdt)}
					</p>
					<h3 class="mt-6 font-medium">Positions</h3>
					{#if connection.report.positions.length === 0}<p
							class="mt-2 text-sm text-muted-foreground"
						>
							No open positions.
						</p>{:else}
						<div class="mt-3 overflow-x-auto">
							<table class="w-full text-left text-sm">
								<thead
									><tr class="border-b border-border text-xs text-muted-foreground"
										><th class="py-2 pr-4">Asset</th><th class="pr-4">Strategy</th><th class="pr-4"
											>Quantity</th
										><th class="pr-4">Value</th><th>Realized P&amp;L</th></tr
									></thead
								><tbody
									>{#each connection.report.positions as position, index (index)}<tr
											class="border-b border-border/50"
											><td class="py-3 pr-4 font-medium">{position.asset}</td><td class="pr-4"
												>{position.strategy === 'dca' ? 'BTC DCA' : 'Trend'}</td
											><td class="pr-4">{quantity(position.quantity)}</td><td class="pr-4"
												>{money(position.quantity * position.price_usdt)}</td
											><td>{money(position.realized_pnl_usdt)}</td></tr
										>{/each}</tbody
								>
							</table>
						</div>
					{/if}
					<h3 class="mt-6 font-medium">Recent fills</h3>
					{#if connection.report.fills.length === 0}<p class="mt-2 text-sm text-muted-foreground">
							No fills reported yet.
						</p>{:else}
						<div class="mt-3 overflow-x-auto">
							<table class="w-full text-left text-sm">
								<thead
									><tr class="border-b border-border text-xs text-muted-foreground"
										><th class="py-2 pr-4">Time</th><th class="pr-4">Trade</th><th class="pr-4"
											>Quantity</th
										><th class="pr-4">Quote value</th><th>Fee</th></tr
									></thead
								><tbody
									>{#each connection.report.fills as fill, index (index)}<tr
											class="border-b border-border/50"
											><td class="py-3 pr-4 whitespace-nowrap">{time(fill.finished_at)}</td><td
												class="pr-4 whitespace-nowrap"
												>{fill.side === 'buy' ? 'Buy' : 'Sell'} {fill.asset}</td
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
						>Disconnect reporting</button
					>
					<p class="mt-2 text-xs text-muted-foreground">
						Disconnecting stops uploads only. Stop trading on the computer or server running your
						executor.
					</p>
				</footer>
			</section>
		{/each}
	{/if}
</main>
