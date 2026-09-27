<script lang="ts">
	// 机会雷达, three tabs. Crypto: the house trend rule's distance-to-trigger for every house
	// coin, the deep-dip list and perp funding extremes (api.opportunity_scan + api.funding_rates,
	// migration 035). US equities / commodities: each daily close against its 52-week closing high
	// and 200-day average, plus VIX (api.market_scan, migration 036) — observations only, since
	// the daily breakout rule lost to buy-and-hold out of sample there. Thresholds live in
	// $lib/scan (same as the Telegram daily_scan digest). Every asset is always listed, the ones
	// past a threshold are highlighted, so no tab is ever empty.
	import type { PageData } from './$types';
	import type { MarketScanRow, OpportunityScan } from '$lib/types';
	import { page } from '$app/stores';
	import { resolve } from '$app/paths';
	import { t, type Lang } from '$lib/i18n';
	import { fmtPct, fmtPrice } from '$lib/utils';
	import {
		SCAN_NEAR,
		SCAN_DIP,
		FUNDING_HOT,
		FUNDING_COLD,
		isNearEntry,
		isNearExit,
		isDip,
		fundingHeat,
		NEAR_HIGH,
		DEEP_DD,
		isNearHigh,
		isDeep,
		summarizeMarket
	} from '$lib/scan';
	import Kpi from '$lib/components/kpi.svelte';
	import Callout from '$lib/components/callout.svelte';
	import AlertSubscribe from '$lib/components/alert-subscribe.svelte';

	let { data }: { data: PageData } = $props();
	const lang = $derived<Lang>(data.lang ?? 'zh');
	const scan = $derived(data.scan ?? []);
	const groups = $derived(data.groups);
	const funding = $derived(data.funding ?? []);

	type Tab = 'crypto' | 'equity' | 'commodity';
	const TABS: Tab[] = ['crypto', 'equity', 'commodity'];
	const initialTab = $page.url.searchParams.get('tab');
	let tab = $state<Tab>(TABS.includes(initialTab as Tab) ? (initialTab as Tab) : 'crypto');
	const equity = $derived(summarizeMarket(data.markets ?? [], 'equity'));
	const commodity = $derived(summarizeMarket(data.markets ?? [], 'commodity'));
	const tabCount = $derived({
		crypto: scan.length,
		equity: equity.rows.length,
		commodity: commodity.rows.length
	});

	function fmt(key: string, vars: Record<string, string | number>) {
		let out = t(lang, key);
		for (const [k, v] of Object.entries(vars)) out = out.replaceAll(`{${k}}`, String(v));
		return out;
	}

	// Fractions in the views → signed percent.
	const pct = (v: number | null | undefined, digits = 1) =>
		v == null ? '—' : fmtPct(v * 100, digits);
	const TH = {
		near: `${Math.round(SCAN_NEAR * 100)}%`,
		dip: `${Math.round(-SCAN_DIP * 100)}%`,
		hot: pct(FUNDING_HOT, 0),
		cold: pct(FUNDING_COLD, 0)
	};
	// Per-interval funding is tiny (0.01% is typical): 4 decimals so it never rounds to 0.
	const rate = (v: number | null) => (v == null ? '—' : fmtPct(v * 100, 4));
	const volume = (v: number | null) =>
		v == null
			? '—'
			: '$' +
				new Intl.NumberFormat(lang === 'en' ? 'en-US' : 'zh-CN', {
					notation: 'compact',
					maximumFractionDigits: 1
				}).format(v);
	// Always UTC: the rule runs on UTC hourly closes.
	const minute = (ts: string | null | undefined) =>
		ts ? new Date(ts).toISOString().slice(0, 16).replace('T', ' ') : '—';
	const latest = (xs: (string | null)[]) =>
		xs
			.filter((v): v is string => v != null)
			.sort()
			.at(-1) ?? null;
	const asOf = $derived(latest(scan.map((r) => r.last_ts)));
	const fundingAsOf = $derived(latest(funding.map((f) => f.updated_at)));

	const nEntry = $derived(scan.filter(isNearEntry).length);
	const nExit = $derived(scan.filter(isNearExit).length);
	const nDip = $derived(scan.filter(isDip).length);
	const nFunding = $derived(funding.filter((f) => fundingHeat(f) != null).length);

	const tone = (v: number | null | undefined) =>
		v == null || v === 0
			? 'text-muted-foreground'
			: v > 0
				? 'text-[var(--profit)]'
				: 'text-[var(--loss)]';
	const HL = {
		entry: 'bg-[color-mix(in_oklab,var(--dawn-500)_10%,transparent)]',
		exit: 'bg-[color-mix(in_oklab,var(--warn)_12%,transparent)]',
		dip: 'bg-[color-mix(in_oklab,var(--loss)_9%,transparent)]',
		hot: 'bg-[color-mix(in_oklab,var(--warn)_12%,transparent)]',
		cold: 'bg-[color-mix(in_oklab,var(--violet-500)_10%,transparent)]'
	};
	const BADGE = {
		entry: 'border-[color-mix(in_oklab,var(--dawn-500)_45%,transparent)] text-[var(--dawn-500)]',
		exit: 'border-[color-mix(in_oklab,var(--warn)_45%,transparent)] text-[var(--warn)]',
		dip: 'border-[color-mix(in_oklab,var(--loss)_45%,transparent)] text-[var(--loss)]',
		hot: 'border-[color-mix(in_oklab,var(--warn)_45%,transparent)] text-[var(--warn)]',
		cold: 'border-[color-mix(in_oklab,var(--violet-500)_45%,transparent)] text-[var(--violet-500)]'
	};
	type Flag = keyof typeof BADGE;

	const MTH = {
		near: `${Math.round(-NEAR_HIGH * 100)}%`,
		deep: `${Math.round(-DEEP_DD * 100)}%`
	};
	// Commodity quotes are in each contract's own unit (grains in US cents per bushel), so no "$".
	const plain = (v: number) =>
		v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	const quote = (r: MarketScanRow, v: number) =>
		r.asset_class === 'equity' ? fmtPrice(v) : plain(v);
	const nameOf = (r: MarketScanRow) => (lang === 'en' ? r.name_en : r.name_zh);
	// The session date of the newest bar (bars are stamped in UTC during the US session).
	const barDay = (rows: MarketScanRow[]) => {
		const ms = Math.max(...rows.map((r) => new Date(r.last_ts).getTime()));
		return Number.isFinite(ms) ? new Date(ms).toISOString().slice(0, 10) : '';
	};
	const vixTone = (v: number) => (v >= 30 ? 'bad' : v >= 20 ? 'warn' : 'default');

	const RISK_KEYS = ['scan.risk.fees', 'scan.risk.flip', 'scan.risk.liq', 'scan.risk.exchange'];
	const th = 'px-2 py-2 sm:px-3';
	const td = 'px-2 py-2 sm:px-3';
</script>

{#snippet badge(flag: Flag, label: string)}
	<span
		class="inline-flex items-center rounded-full border px-1.5 py-px text-[10px] font-medium whitespace-nowrap {BADGE[
			flag
		]}">{label}</span
	>
{/snippet}

<!-- The coin cell: name links to its full history on /record, flag badge + optional sub-line under it. -->
{#snippet coin(r: OpportunityScan, flag: Flag | null, flagLabel: string, sub: string = '')}
	<td class="{td} align-top">
		<a
			href={resolve('/record')}
			class="font-semibold text-foreground hover:text-primary hover:underline">{r.asset}</a
		>
		{#if flag}<div class="mt-0.5">{@render badge(flag, flagLabel)}</div>{/if}
		{#if sub}<div class="bdv-num mt-0.5 text-[10px] text-muted-foreground">{sub}</div>{/if}
	</td>
{/snippet}

{#snippet sectionHead(title: string, sub: string)}
	<h2 class="text-lg font-semibold tracking-tight">{title}</h2>
	<p class="mt-1 text-sm text-muted-foreground">{sub}</p>
{/snippet}

<!-- US equities / commodities tab: KPIs, the "why no trigger" note, one table sorted by distance
     to the 52-week closing high. -->
{#snippet market(cls: 'equity' | 'commodity', m: ReturnType<typeof summarizeMarket>)}
	<section class="mt-6">
		<p class="max-w-3xl text-sm leading-relaxed text-muted-foreground">
			{t(lang, `scan.mkt.${cls}.sub`)}
		</p>
		{#if m.rows.length}
			<p class="mt-2 text-xs text-muted-foreground">
				{fmt('scan.mkt.asOf', { d: barDay(m.rows) })}
			</p>
		{/if}
	</section>

	{#if !m.rows.length}
		<div class="mt-8 rounded-xl border border-dashed border-border bg-card p-8 text-center">
			<div class="text-sm font-semibold text-foreground">
				{t(lang, data.marketsFailed ? 'scan.error.title' : 'scan.mkt.empty.title')}
			</div>
			<p class="mt-2 text-sm text-muted-foreground">
				{t(lang, data.marketsFailed ? 'scan.error.body' : 'scan.mkt.empty.body')}
			</p>
		</div>
	{:else}
		<section
			class="mt-6 grid grid-cols-2 gap-3 {cls === 'equity' ? 'sm:grid-cols-4' : 'sm:grid-cols-3'}"
		>
			{#if cls === 'equity'}
				<Kpi
					label={t(lang, 'scan.mkt.kpi.vix')}
					value={data.vix ? data.vix.value.toFixed(1) : '—'}
					sub={t(lang, 'scan.mkt.kpi.vixSub')}
					tone={data.vix ? vixTone(data.vix.value) : 'default'}
				/>
			{/if}
			<Kpi
				label={t(lang, 'scan.mkt.kpi.nearHigh')}
				value={m.nearHigh}
				sub={fmt('scan.mkt.kpi.nearHighSub', { near: MTH.near })}
			/>
			<Kpi
				label={t(lang, 'scan.mkt.kpi.deep')}
				value={m.deep}
				sub={fmt('scan.mkt.kpi.deepSub', { deep: MTH.deep })}
				tone={m.deep ? 'bad' : 'default'}
			/>
			<Kpi
				label={t(lang, 'scan.mkt.kpi.aboveMa')}
				value={`${m.aboveMa}/${m.rows.length}`}
				sub={t(lang, 'scan.mkt.kpi.aboveMaSub')}
			/>
		</section>

		<section class="mt-8">
			{@render sectionHead(
				t(lang, 'scan.mkt.table.title'),
				fmt('scan.mkt.table.sub', { near: MTH.near, deep: MTH.deep })
			)}
			<div class="mt-4 overflow-x-auto rounded-lg border border-border">
				<table class="w-full text-left text-xs">
					<thead class="bg-secondary/50 text-muted-foreground">
						<tr>
							<th class={th}>{t(lang, `scan.mkt.col.${cls}`)}</th>
							<th class="{th} text-right">{t(lang, 'scan.col.last')}</th>
							<th class="{th} hidden text-right sm:table-cell">{t(lang, 'scan.mkt.col.high52w')}</th
							>
							<th class="{th} text-right">{t(lang, 'scan.mkt.col.fromHigh')}</th>
							<th class="{th} text-right">{t(lang, 'scan.mkt.col.vsMa')}</th>
							<th class="{th} hidden text-right sm:table-cell">{t(lang, 'scan.mkt.col.ret1m')}</th>
						</tr>
					</thead>
					<tbody>
						{#each m.rows as r (r.asset)}
							{@const near = isNearHigh(r)}
							{@const deep = isDeep(r)}
							<tr class="border-t border-border {near ? HL.entry : deep ? HL.dip : ''}">
								<td class="{td} align-top">
									<span class="font-semibold text-foreground">
										{cls === 'commodity' ? (nameOf(r) ?? r.asset) : r.asset}
									</span>
									{#if near}<div class="mt-0.5">
											{@render badge('entry', fmt('scan.mkt.flag.near', { near: MTH.near }))}
										</div>{:else if deep}<div class="mt-0.5">
											{@render badge('dip', fmt('scan.mkt.flag.deep', { deep: MTH.deep }))}
										</div>{/if}
									<div class="mt-0.5 text-[10px] text-muted-foreground">
										{[cls === 'equity' ? nameOf(r) : r.asset, t(lang, `scan.mkt.grp.${r.grp}`)]
											.filter(Boolean)
											.join(' · ')}
									</div>
								</td>
								<td class="{td} bdv-num text-right align-top">{quote(r, r.last_close)}</td>
								<td
									class="{td} bdv-num hidden text-right align-top text-muted-foreground sm:table-cell"
									>{quote(r, r.high_52w)}</td
								>
								<td
									class="{td} bdv-num text-right align-top font-medium {near
										? 'text-[var(--dawn-500)]'
										: deep
											? 'text-[var(--loss)]'
											: 'text-foreground'}">{pct(r.from_high_52w)}</td
								>
								<td class="{td} bdv-num text-right align-top {tone(r.vs_ma200)}"
									>{pct(r.vs_ma200)}</td
								>
								<td class="{td} bdv-num hidden text-right align-top sm:table-cell {tone(r.ret_1m)}"
									>{pct(r.ret_1m)}</td
								>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			{#if cls === 'commodity'}
				<p class="mt-2 text-xs text-muted-foreground">{t(lang, 'scan.mkt.unitNote')}</p>
			{/if}
		</section>

		<div class="mt-2">
			<Callout type="info" title={t(lang, 'scan.mkt.why.title')}>
				<p>{t(lang, `scan.mkt.why.${cls}`)}</p>
				<p class="mt-2">{t(lang, 'scan.mkt.why.use')}</p>
			</Callout>
		</div>
	{/if}
{/snippet}

<svelte:head>
	<title>{t(lang, 'scan.metaTitle')} · BearDawnVerse Quant</title>
	<meta name="description" content={t(lang, 'scan.metaDesc')} />
	<meta property="og:title" content="{t(lang, 'scan.metaTitle')} · BearDawnVerse Quant" />
	<meta property="og:description" content={t(lang, 'scan.metaDesc')} />
</svelte:head>

<main class="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
	<header>
		<div class="bdv-eyebrow mb-2 text-[var(--gold-500)]">{t(lang, 'scan.eyebrow')}</div>
		<h1 class="text-2xl font-bold tracking-tight sm:text-3xl">{t(lang, 'scan.title')}</h1>
		<p class="mt-3 max-w-3xl text-sm leading-relaxed text-muted-foreground">
			{t(lang, 'scan.lead')}
		</p>
	</header>

	<!-- Asset-class tabs (?tab=equity|commodity deep-links one). -->
	<div
		role="tablist"
		aria-label={t(lang, 'scan.title')}
		class="mt-6 flex gap-1 overflow-x-auto rounded-lg border border-border bg-card p-1"
	>
		{#each TABS as k (k)}
			<button
				type="button"
				role="tab"
				aria-selected={tab === k}
				class="flex-1 rounded-md px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-colors {tab ===
				k
					? 'bg-primary text-primary-foreground'
					: 'text-muted-foreground hover:bg-accent hover:text-foreground'}"
				onclick={() => (tab = k)}
			>
				{t(lang, `scan.tab.${k}`)}
				{#if tabCount[k]}<span class="ml-1 text-xs opacity-70">{tabCount[k]}</span>{/if}
			</button>
		{/each}
	</div>

	{#if tab === 'crypto'}
		<section class="mt-6">
			{#if scan.length}
				<p class="mt-3 max-w-3xl text-sm leading-relaxed text-muted-foreground">
					{fmt('scan.subtitle', { n: scan.length })}
				</p>
				<p class="mt-2 text-xs text-muted-foreground">
					{[
						asOf ? fmt('scan.asOf', { ts: minute(asOf) }) : '',
						fundingAsOf ? fmt('scan.fundingAsOf', { ts: minute(fundingAsOf) }) : ''
					]
						.filter(Boolean)
						.join(lang === 'en' ? ' ' : '')}
				</p>
			{/if}
		</section>

		{#if !scan.length}
			<div class="mt-8 rounded-xl border border-dashed border-border bg-card p-8 text-center">
				<div class="text-sm font-semibold text-foreground">
					{t(lang, data.failed ? 'scan.error.title' : 'scan.empty.title')}
				</div>
				<p class="mt-2 text-sm text-muted-foreground">
					{t(lang, data.failed ? 'scan.error.body' : 'scan.empty.body')}
				</p>
			</div>
		{:else}
			<!-- Counts past each threshold — the same four lines the morning digest leads with. -->
			<section class="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
				<Kpi
					label={t(lang, 'scan.kpi.nearEntry')}
					value={nEntry}
					sub={fmt('scan.kpi.nearEntrySub', { near: TH.near })}
				/>
				<Kpi
					label={t(lang, 'scan.kpi.nearExit')}
					value={nExit}
					sub={fmt('scan.kpi.nearExitSub', { near: TH.near })}
					tone={nExit ? 'warn' : 'default'}
				/>
				<Kpi
					label={t(lang, 'scan.kpi.dip')}
					value={nDip}
					sub={fmt('scan.kpi.dipSub', { dip: TH.dip })}
					tone={nDip ? 'bad' : 'default'}
				/>
				<Kpi
					label={t(lang, 'scan.kpi.funding')}
					value={nFunding}
					sub={fmt('scan.kpi.fundingSub', { hot: TH.hot, cold: TH.cold })}
				/>
			</section>

			<!-- (1) Near the buy trigger (flat) and near the exit line (held): every house coin is in one. -->
			<div class="mt-10 grid gap-10 lg:grid-cols-2 lg:gap-6">
				<section>
					{@render sectionHead(
						t(lang, 'scan.entry.title'),
						fmt('scan.entry.sub', { near: TH.near })
					)}
					{#if groups.entry.length}
						<div class="mt-4 overflow-x-auto rounded-lg border border-border">
							<table class="w-full text-left text-xs">
								<thead class="bg-secondary/50 text-muted-foreground">
									<tr>
										<th class={th}>{t(lang, 'scan.col.asset')}</th>
										<th class="{th} text-right">{t(lang, 'scan.col.last')}</th>
										<th class="{th} text-right">{t(lang, 'scan.col.trigger')}</th>
										<th class="{th} text-right">{t(lang, 'scan.col.toEntry')}</th>
									</tr>
								</thead>
								<tbody>
									{#each groups.entry as r (r.asset)}
										{@const near = isNearEntry(r)}
										<tr class="border-t border-border {near ? HL.entry : ''}">
											{@render coin(
												r,
												near ? 'entry' : null,
												fmt('scan.flag.near', { near: TH.near })
											)}
											<td class="{td} bdv-num text-right">{fmtPrice(r.last_close)}</td>
											<td class="{td} bdv-num text-right">{fmtPrice(r.channel_high)}</td>
											<td
												class="{td} bdv-num text-right font-medium {near
													? 'text-[var(--dawn-500)]'
													: 'text-foreground'}">{pct(r.to_entry)}</td
											>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					{:else}
						<p
							class="mt-4 rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground"
						>
							{t(lang, 'scan.none.entry')}
						</p>
					{/if}
				</section>

				<section>
					{@render sectionHead(t(lang, 'scan.exit.title'), fmt('scan.exit.sub', { near: TH.near }))}
					{#if groups.exit.length}
						<div class="mt-4 overflow-x-auto rounded-lg border border-border">
							<table class="w-full text-left text-xs">
								<thead class="bg-secondary/50 text-muted-foreground">
									<tr>
										<th class={th}>{t(lang, 'scan.col.asset')}</th>
										<th class="{th} text-right">{t(lang, 'scan.col.last')}</th>
										<th class="{th} text-right">{t(lang, 'scan.col.exitLine')}</th>
										<th class="{th} text-right">{t(lang, 'scan.col.toExit')}</th>
									</tr>
								</thead>
								<tbody>
									{#each groups.exit as r (r.asset)}
										{@const near = isNearExit(r)}
										<tr class="border-t border-border {near ? HL.exit : ''}">
											{@render coin(
												r,
												near ? 'exit' : null,
												fmt('scan.flag.near', { near: TH.near }),
												r.held_since
													? fmt('scan.heldSince', { ts: minute(r.held_since).slice(0, 10) })
													: ''
											)}
											<td class="{td} bdv-num text-right align-top">{fmtPrice(r.last_close)}</td>
											<td class="{td} bdv-num text-right align-top">{fmtPrice(r.channel_low)}</td>
											<td
												class="{td} bdv-num text-right align-top font-medium {near
													? 'text-[var(--warn)]'
													: 'text-foreground'}">{pct(r.to_exit)}</td
											>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					{:else}
						<p
							class="mt-4 rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground"
						>
							{t(lang, 'scan.none.exit')}
						</p>
					{/if}
				</section>
			</div>

			<!-- (2) Distance from the 30-day high, every coin. -->
			<section class="mt-10">
				{@render sectionHead(t(lang, 'scan.dip.title'), fmt('scan.dip.sub', { dip: TH.dip }))}
				<div class="mt-4 overflow-x-auto rounded-lg border border-border">
					<table class="w-full text-left text-xs">
						<thead class="bg-secondary/50 text-muted-foreground">
							<tr>
								<th class={th}>{t(lang, 'scan.col.asset')}</th>
								<th class="{th} text-right">{t(lang, 'scan.col.last')}</th>
								<th class="{th} text-right">{t(lang, 'scan.col.high30d')}</th>
								<th class="{th} text-right">{t(lang, 'scan.col.fromHigh')}</th>
							</tr>
						</thead>
						<tbody>
							{#each groups.dip as r (r.asset)}
								{@const dip = isDip(r)}
								<tr class="border-t border-border {dip ? HL.dip : ''}">
									{@render coin(r, dip ? 'dip' : null, t(lang, 'scan.flag.dip'))}
									<td class="{td} bdv-num text-right">{fmtPrice(r.last_close)}</td>
									<td class="{td} bdv-num text-right">{fmtPrice(r.high_30d)}</td>
									<td class="{td} bdv-num text-right font-medium {tone(r.from_high_30d)}"
										>{pct(r.from_high_30d)}</td
									>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				{#if scan.some((r) => r.from_high_30d == null)}
					<p class="mt-2 text-xs text-muted-foreground">{t(lang, 'scan.dip.noData')}</p>
				{/if}
				<p class="mt-3 text-xs text-muted-foreground">
					{t(lang, 'scan.recordLink')}
					<a href={resolve('/record')} class="font-medium text-primary hover:underline"
						>{t(lang, 'scan.recordCta')}</a
					>
				</p>
			</section>

			<!-- (3) Perp funding, hottest first, with the honest carry explainer. -->
			<section class="mt-10">
				{@render sectionHead(
					t(lang, 'scan.funding.title'),
					fmt('scan.funding.sub', { n: funding.length, hot: TH.hot, cold: TH.cold })
				)}
				{#if funding.length}
					<div class="mt-4 overflow-x-auto rounded-lg border border-border">
						<table class="w-full text-left text-xs">
							<thead class="bg-secondary/50 text-muted-foreground">
								<tr>
									<th class={th}>{t(lang, 'scan.funding.col.asset')}</th>
									<th class="{th} text-right">{t(lang, 'scan.funding.col.ann')}</th>
									<th class="{th} text-right">{t(lang, 'scan.funding.col.last')}</th>
									<th class="{th} text-right">{t(lang, 'scan.funding.col.vol')}</th>
								</tr>
							</thead>
							<tbody>
								{#each funding as f (f.symbol)}
									{@const heat = fundingHeat(f)}
									<tr class="border-t border-border {heat ? HL[heat] : ''}">
										<td class="{td} align-top">
											<span class="font-semibold text-foreground">{f.asset}</span>
											{#if heat}<div class="mt-0.5">
													{@render badge(heat, t(lang, `scan.funding.${heat}`))}
												</div>{/if}
										</td>
										<td
											class="{td} bdv-num text-right align-top font-medium {heat === 'hot'
												? 'text-[var(--warn)]'
												: heat === 'cold'
													? 'text-[var(--violet-500)]'
													: 'text-foreground'}">{pct(f.ann_7d)}</td
										>
										<td class="{td} bdv-num text-right align-top text-muted-foreground"
											>{rate(f.last_rate)}</td
										>
										<td class="{td} bdv-num text-right align-top text-muted-foreground"
											>{volume(f.quote_volume_24h)}</td
										>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{:else}
					<p
						class="mt-4 rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground"
					>
						{t(lang, 'scan.funding.empty')}
					</p>
				{/if}
				<div class="md:grid md:grid-cols-2 md:gap-x-4">
					<Callout type="info" title={t(lang, 'scan.carry.title')}>
						<p>{t(lang, 'scan.carry.what')}</p>
						<p class="mt-2">{t(lang, 'scan.carry.how')}</p>
						<p class="mt-2">{t(lang, 'scan.carry.backtest')}</p>
					</Callout>
					<Callout type="warning" title={t(lang, 'scan.risk.title')}>
						<ul class="flex list-disc flex-col gap-1 pl-4">
							{#each RISK_KEYS as k (k)}
								<li>{t(lang, k)}</li>
							{/each}
						</ul>
					</Callout>
				</div>
			</section>
		{/if}
	{:else}
		{@render market(tab, tab === 'equity' ? equity : commodity)}
	{/if}

	<!-- CTA: the Telegram subscription card (topic daily_scan). -->
	<section id="alerts" class="mt-10">
		<h2 class="text-lg font-semibold tracking-tight">{t(lang, 'scan.cta.title')}</h2>
		<p class="mt-1 mb-4 text-sm text-muted-foreground">{t(lang, 'scan.cta.sub')}</p>
		<AlertSubscribe />
	</section>

	<p class="mt-6 text-xs text-muted-foreground">⚠️ {t(lang, 'scan.disclaimer')}</p>
</main>
