<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { session, getToken } from '$lib/auth';
	import { fmtUSD, fmtTime } from '$lib/utils';
	import { t, type Lang } from '$lib/i18n';
	import AffiliateCta from './affiliate-cta.svelte';

	interface Holding {
		asset: string;
		total: number;
		usd_value: number;
		usd_price: number | null;
	}

	const lang = $derived<Lang>($page.data.lang ?? 'zh');

	let connected = $state(false);
	let connectedAt = $state<string | null>(null);
	let total = $state(0);
	let holdings = $state<Holding[]>([]);
	let loading = $state(false);
	let saving = $state(false);
	let err = $state('');

	let showForm = $state(false);
	let apiKey = $state('');
	let apiSecret = $state('');

	async function refresh() {
		const tok = getToken();
		if (!tok) return;
		loading = true;
		err = '';
		try {
			const r = await fetch('/api/portfolio', { headers: { Authorization: `Bearer ${tok}` } });
			const j = await r.json();
			if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
			connected = Boolean(j.connected);
			connectedAt = j.connected_at ?? null;
			total = j.total_usd ?? 0;
			holdings = j.holdings ?? [];
			if (connected) showForm = false;
		} catch (e) {
			err = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	async function connect() {
		const tok = getToken();
		if (!tok || !apiKey || !apiSecret) return;
		saving = true;
		err = '';
		try {
			const r = await fetch('/api/portfolio', {
				method: 'POST',
				headers: {
					Authorization: `Bearer ${tok}`,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({ apiKey, apiSecret })
			});
			const j = await r.json();
			if (!r.ok) throw new Error(j.error ?? `HTTP ${r.status}`);
			apiKey = '';
			apiSecret = '';
			await refresh();
		} catch (e) {
			err = (e as Error).message;
		} finally {
			saving = false;
		}
	}

	async function disconnect() {
		const tok = getToken();
		if (!tok) return;
		saving = true;
		err = '';
		try {
			await fetch('/api/portfolio', {
				method: 'DELETE',
				headers: { Authorization: `Bearer ${tok}` }
			});
			connected = false;
			connectedAt = null;
			total = 0;
			holdings = [];
		} catch (e) {
			err = (e as Error).message;
		} finally {
			saving = false;
		}
	}

	function fmt(key: string, vars: Record<string, string>) {
		let s = t(lang, key);
		for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, v);
		return s;
	}

	onMount(() => {
		if ($session) refresh();
	});
</script>

{#if $session}
	<section class="mt-6 rounded-lg border bg-card p-5">
		<div class="flex flex-wrap items-baseline justify-between gap-3">
			<div>
				<h3 class="text-sm font-semibold">{t(lang, 'binance.title')}</h3>
				{#if !connected}
					<p class="mt-1 text-xs text-muted-foreground">{t(lang, 'binance.subtitle')}</p>
				{:else if connectedAt}
					<p class="mt-1 text-xs text-muted-foreground">
						✓ {t(lang, 'binance.connected')} · {fmt('binance.connectedAt', {
							time: fmtTime(connectedAt)
						})}
					</p>
				{/if}
			</div>
			{#if connected}
				<div class="flex items-center gap-2">
					<button
						type="button"
						onclick={refresh}
						disabled={loading}
						class="rounded-md border border-border bg-secondary px-3 py-1.5 text-xs text-secondary-foreground hover:bg-accent disabled:opacity-50"
					>
						{loading ? '…' : t(lang, 'binance.refresh')}
					</button>
					<button
						type="button"
						onclick={disconnect}
						disabled={saving}
						class="rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent disabled:opacity-50"
					>
						{t(lang, 'binance.disconnect')}
					</button>
				</div>
			{:else}
				<button
					type="button"
					onclick={() => (showForm = !showForm)}
					class="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground hover:opacity-90"
				>
					{t(lang, 'binance.connect')}
				</button>
			{/if}
		</div>

		{#if !connected && !showForm}
			<AffiliateCta variant="inline" />
		{/if}

		{#if !connected && showForm}
			<div class="mt-4 rounded-md border border-dashed bg-background/50 p-4 text-xs">
				<p class="mb-3 text-muted-foreground">{t(lang, 'binance.howto')}</p>
				<label class="mt-2 flex flex-col gap-1">
					<span class="text-muted-foreground">{t(lang, 'binance.apiKey')}</span>
					<input
						type="text"
						bind:value={apiKey}
						autocomplete="off"
						spellcheck="false"
						class="rounded-md border border-border bg-background px-3 py-2 font-mono text-foreground"
					/>
				</label>
				<label class="mt-3 flex flex-col gap-1">
					<span class="text-muted-foreground">{t(lang, 'binance.apiSecret')}</span>
					<input
						type="password"
						bind:value={apiSecret}
						autocomplete="off"
						spellcheck="false"
						class="rounded-md border border-border bg-background px-3 py-2 font-mono text-foreground"
					/>
				</label>
				<div class="mt-4 flex gap-2">
					<button
						type="button"
						onclick={connect}
						disabled={saving || !apiKey || !apiSecret}
						class="flex-1 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50"
					>
						{saving ? '…' : t(lang, 'binance.connect')}
					</button>
					<button
						type="button"
						onclick={() => (showForm = false)}
						class="rounded-md border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-accent"
					>
						✕
					</button>
				</div>
			</div>
		{/if}

		{#if connected}
			<div class="mt-4 rounded-md bg-background/40 p-4">
				<div class="flex items-baseline justify-between">
					<span class="text-xs text-muted-foreground uppercase">{t(lang, 'binance.totalUsd')}</span>
					<span class="font-mono text-2xl font-semibold">{fmtUSD(total)}</span>
				</div>
			</div>

			{#if loading}
				<p class="mt-3 text-xs text-muted-foreground">{t(lang, 'binance.loading')}</p>
			{:else if holdings.length === 0}
				<p class="mt-3 text-xs text-muted-foreground">{t(lang, 'binance.empty')}</p>
			{:else}
				<div class="mt-3 overflow-hidden rounded-md border">
					<table class="w-full text-xs">
						<thead class="bg-secondary text-left text-[10px] text-muted-foreground uppercase">
							<tr>
								<th class="px-3 py-2">{t(lang, 'binance.table.asset')}</th>
								<th class="px-3 text-right">{t(lang, 'binance.table.amount')}</th>
								<th class="px-3 text-right">{t(lang, 'binance.table.price')}</th>
								<th class="px-3 text-right">{t(lang, 'binance.table.value')}</th>
							</tr>
						</thead>
						<tbody class="font-mono">
							{#each holdings.slice(0, 15) as h (h.asset)}
								<tr class="border-t border-border">
									<td class="px-3 py-1.5 font-semibold">{h.asset}</td>
									<td class="px-3 text-right">{h.total.toFixed(h.total < 1 ? 4 : 2)}</td>
									<td class="px-3 text-right text-muted-foreground">
										{h.usd_price == null ? '—' : fmtUSD(h.usd_price)}
									</td>
									<td class="px-3 text-right">{fmtUSD(h.usd_value)}</td>
								</tr>
							{/each}
							{#if holdings.length > 15}
								<tr class="border-t border-border">
									<td class="px-3 py-2 text-center text-muted-foreground" colspan="4">
										+{holdings.length - 15} more
									</td>
								</tr>
							{/if}
						</tbody>
					</table>
				</div>
			{/if}
		{/if}

		{#if err}
			<p class="mt-3 text-xs text-red-500">{fmt('binance.error', { msg: err })}</p>
		{/if}
	</section>
{/if}
