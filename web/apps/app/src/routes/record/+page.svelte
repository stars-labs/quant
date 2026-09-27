<script lang="ts">
	// 策略战绩 — public track record of the house trend rule (Donchian 1h breakout) on
	// the house coin universe
	// (api.strategy_record + api.strategy_trades, migration 032). Every stat comes from
	// strategy_record; the load only averages across assets. Honesty rules: returns are net of
	// 0.1% fee per side, buy-and-hold and win rate always sit next to the strategy return, and
	// backfilled trades carry a "Backfilled" badge wherever they appear. Live-only stats
	// (api.strategy_live_record) sit in their own block with a small-sample note; logged-in
	// users can mark live trades they followed (api.user_follows, owner-only) and see their own
	// record (我的跟单) — both migration 037.
	import type { PageData } from './$types';
	import type { MyFollow, MyFollowRecord, StrategyRecord, StrategyTrade } from '$lib/types';
	import { resolve } from '$app/paths';
	import { t, type Lang } from '$lib/i18n';
	import { fmtPct, fmtPrice } from '$lib/utils';
	import Kpi from '$lib/components/kpi.svelte';
	import StatusPill from '$lib/components/status-pill.svelte';
	import Callout from '$lib/components/callout.svelte';
	import AlertSubscribe from '$lib/components/alert-subscribe.svelte';
	import MyFollows from './my-follows.svelte';
	import { user } from '$lib/auth';
	import { followTrade, getMyFollowRecord, getMyFollows, unfollowTrade } from '$lib/alerts';
	import { LIVE_MIN_SAMPLE, liveSummary } from '$lib/growth';

	let { data }: { data: PageData } = $props();
	const lang = $derived<Lang>(data.lang ?? 'zh');
	const s = $derived(data.summary);
	const record = $derived<StrategyRecord[]>(data.record ?? []);
	const trades = $derived<StrategyTrade[]>(data.trades ?? []);
	// undefined = the live-record request failed → the block is hidden, nothing else is.
	const live = $derived(data.live === undefined ? null : liveSummary(data.live));

	// ── 我的跟单: client-side, only for a logged-in user (the views are owner-only).
	let follows = $state<MyFollow[]>([]);
	let mine = $state<MyFollowRecord | null>(null);
	let mineStatus = $state<'loading' | 'ready' | 'error'>('loading');
	let busyId = $state<number | null>(null);
	const followed = $derived(new Set(follows.map((f) => f.trade_id)));
	let scrolledToMine = false;

	async function loadMine() {
		try {
			[follows, mine] = await Promise.all([getMyFollows(), getMyFollowRecord()]);
			mineStatus = 'ready';
			// Telegram /me links to #mine, which only exists once this section has rendered.
			if (!scrolledToMine && location.hash === '#mine') {
				scrolledToMine = true;
				requestAnimationFrame(() => document.getElementById('mine')?.scrollIntoView());
			}
		} catch {
			mineStatus = 'error';
		}
	}

	$effect(() => {
		if ($user?.sub) {
			mineStatus = 'loading';
			void loadMine();
		} else {
			follows = [];
			mine = null;
		}
	});

	async function toggleFollow(tradeId: number) {
		if (busyId != null) return;
		busyId = tradeId;
		try {
			if (followed.has(tradeId)) await unfollowTrade(tradeId);
			else await followTrade(tradeId);
			await loadMine();
		} catch {
			mineStatus = 'error';
		} finally {
			busyId = null;
		}
	}

	const PREVIEW = 12;
	let showAll = $state(false);
	const shown = $derived(showAll ? trades : trades.slice(0, PREVIEW));

	// Open trades have no net_ret in the view; mark them with strategy_record.open_ret (the same
	// mark-to-market, both fees) so the table never invents its own number.
	const openByAsset = $derived<Record<string, StrategyRecord>>(
		Object.fromEntries(record.filter((r) => r.open_entry_ts != null).map((r) => [r.asset, r]))
	);

	const RULE_KEYS = [
		'record.rules.buy',
		'record.rules.sell',
		'record.rules.scope',
		'record.rules.portfolio',
		'record.rules.universe',
		'record.rules.fees'
	];

	function fmt(key: string, vars: Record<string, string | number>) {
		let out = t(lang, key);
		for (const [k, v] of Object.entries(vars)) out = out.replaceAll(`{${k}}`, String(v));
		return out;
	}

	// Returns are fractions in the view → signed percent.
	const pct = (v: number | null | undefined) => (v == null ? '—' : fmtPct(v * 100, 1));
	const dollars = (v: number) => '$' + Math.round(v).toLocaleString('en-US');
	// Always UTC: signals fire on UTC hourly closes, whatever the server or browser zone is.
	const utc = (ts: string | null | undefined) => (ts ? new Date(ts).toISOString() : '');
	const day = (ts: string | null | undefined) => utc(ts).slice(0, 10) || '—';
	const minute = (ts: string | null | undefined) => utc(ts).slice(0, 16).replace('T', ' ') || '—';
	const winRate = (v: number | null) => (v == null ? '—' : `${Math.round(v * 100)}%`);

	const usd1k = (ret: number) => `$${Math.round(1000 * (1 + ret)).toLocaleString('en-US')}`;
	// Link previews (Telegram/WeChat/X) carry the live numbers, so a forwarded link sells itself.
	const metaDesc = $derived(
		s
			? fmt('record.metaDescLive', {
					start: day(s.startTs),
					follow: usd1k(s.portfolioRet),
					hold: usd1k(s.holdRet),
					n: s.nClosed,
					win: winRate(s.winRate)
				})
			: t(lang, 'record.metaDesc')
	);

	let copied = $state(false);
	async function share() {
		const url = window.location.origin + window.location.pathname;
		const title = t(lang, 'record.metaTitle');
		try {
			if (navigator.share) {
				await navigator.share({ title, text: metaDesc, url });
				return;
			}
			await navigator.clipboard.writeText(`${metaDesc}\n${url}`);
			copied = true;
			setTimeout(() => (copied = false), 2000);
		} catch {
			// user dismissed the share sheet / clipboard blocked — nothing to do
		}
	}
	const dist = (level: number | null, last: number | null) =>
		level != null && last ? level / last - 1 : null;
	const tone = (v: number | null | undefined) =>
		v == null || v === 0
			? 'text-muted-foreground'
			: v > 0
				? 'text-[var(--profit)]'
				: 'text-[var(--loss)]';
	const kpiTone = (v: number) => (v > 0 ? 'good' : v < 0 ? 'bad' : 'default');
	// Name the coins while the list is short; past 4 a count reads better than a wall of tickers.
	const assetList = (xs: string[]) =>
		xs.length > 4
			? fmt('record.assets.count', { n: xs.length })
			: lang === 'en' && xs.length > 1
				? `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`
				: xs.join('、');

	function floating(tr: StrategyTrade): number | null {
		const r = openByAsset[tr.asset];
		if (!r?.open_entry_ts) return null;
		return new Date(r.open_entry_ts).getTime() === new Date(tr.entry_ts).getTime()
			? r.open_ret
			: null;
	}
	const heldDays = (v: number | null) =>
		v == null ? '—' : fmt('record.trades.days', { n: Number(v).toFixed(1) });
</script>

{#snippet sourceBadge(live: boolean)}
	<span
		class="inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium whitespace-nowrap {live
			? 'border-[color-mix(in_oklab,var(--dawn-500)_45%,transparent)] text-[var(--dawn-500)]'
			: 'border-border bg-muted text-muted-foreground'}"
		title={t(lang, live ? 'record.src.liveHint' : 'record.src.backfillHint')}
		>{t(lang, live ? 'record.src.live' : 'record.src.backfill')}</span
	>
{/snippet}

{#snippet followButton(tr: StrategyTrade)}
	{#if tr.live}
		{@const on = followed.has(tr.id)}
		<button
			type="button"
			aria-pressed={on}
			disabled={busyId != null}
			title={t(lang, on ? 'record.follow.unmark' : 'record.follow.markHint')}
			onclick={() => toggleFollow(tr.id)}
			class="rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap transition-colors disabled:opacity-50 {on
				? 'border-[var(--profit)] text-[var(--profit)]'
				: 'border-border text-muted-foreground hover:bg-accent hover:text-foreground'}"
			>{t(lang, on ? 'record.follow.marked' : 'record.follow.mark')}</button
		>
	{:else}
		<span class="text-[11px] text-muted-foreground" title={t(lang, 'record.follow.backfillHint')}
			>—</span
		>
	{/if}
{/snippet}

{#snippet stat(label: string, value: string, cls: string = 'text-foreground')}
	<div class="flex items-baseline justify-between gap-3">
		<span class="text-muted-foreground">{label}</span>
		<span class="bdv-num text-right {cls}">{value}</span>
	</div>
{/snippet}

<svelte:head>
	<title>{t(lang, 'record.metaTitle')} · BearDawnVerse Quant</title>
	<meta name="description" content={metaDesc} />
	<meta property="og:title" content="{t(lang, 'record.metaTitle')} · BearDawnVerse Quant" />
	<meta property="og:description" content={metaDesc} />
</svelte:head>

<main class="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
	<header>
		<div class="bdv-eyebrow mb-2 text-[var(--gold-500)]">{t(lang, 'record.eyebrow')}</div>
		<div class="flex flex-wrap items-center justify-between gap-3">
			<h1 class="text-2xl font-bold tracking-tight sm:text-3xl">{t(lang, 'record.title')}</h1>
			{#if s}
				<button
					type="button"
					onclick={share}
					class="rounded-md border border-border bg-secondary px-3 py-1.5 text-xs font-medium text-secondary-foreground transition-colors hover:bg-accent"
					>{t(lang, copied ? 'record.shareCopied' : 'record.share')}</button
				>
			{/if}
		</div>
		{#if s}
			<p class="mt-3 max-w-3xl text-sm leading-relaxed text-muted-foreground">
				{fmt('record.subtitle', { start: day(s.startTs), assets: assetList(s.assets) })}
			</p>
		{/if}
	</header>

	{#if !s}
		<div class="mt-8 rounded-xl border border-dashed border-border bg-card p-8 text-center">
			<div class="text-sm font-semibold text-foreground">
				{t(lang, data.failed ? 'record.error.title' : 'record.empty.title')}
			</div>
			<p class="mt-2 text-sm text-muted-foreground">
				{t(lang, data.failed ? 'record.error.body' : 'record.empty.body')}
			</p>
		</div>
	{:else}
		<!-- (1) Headline: $1,000 following every signal vs buy-and-hold, same weight, same start. -->
		<section class="mt-8">
			<h2 class="text-sm font-medium text-foreground">
				{fmt('record.headline', { start: day(s.startTs), assets: assetList(s.assets) })}
			</h2>
			<div class="mt-3 grid grid-cols-2 gap-3">
				<Kpi
					label={t(lang, 'record.kpi.follow')}
					value={dollars(1000 * (1 + s.portfolioRet))}
					sub={fmt('record.kpi.followSub', { ret: pct(s.portfolioRet) })}
					tone={kpiTone(s.portfolioRet)}
				/>
				<Kpi
					label={t(lang, 'record.kpi.hold')}
					value={dollars(1000 * (1 + s.holdRet))}
					sub={fmt('record.kpi.holdSub', { ret: pct(s.holdRet) })}
					tone={kpiTone(s.holdRet)}
				/>
			</div>
			<div class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
				<Kpi
					label={t(lang, 'record.kpi.trades')}
					value={s.nClosed}
					sub={s.nOpen
						? fmt('record.kpi.tradesSub', { n: s.nOpen })
						: t(lang, 'record.kpi.tradesSubNone')}
				/>
				<Kpi
					label={t(lang, 'record.kpi.winRate')}
					value={winRate(s.winRate)}
					sub={fmt('record.kpi.winRateSub', { n: s.nClosed, w: s.nWins })}
				/>
				<div class="col-span-2 sm:col-span-1">
					<Kpi
						label={t(lang, 'record.kpi.best')}
						value={s.best ? pct(s.best.ret) : '—'}
						sub={s.best ? fmt('record.kpi.bestSub', { asset: s.best.asset }) : ''}
						tone={s.best ? kpiTone(s.best.ret) : 'default'}
					/>
				</div>
			</div>
			<p class="mt-3 text-xs text-muted-foreground">
				{[
					s.asOf ? fmt('record.asOf', { ts: minute(s.asOf) }) : '',
					fmt('record.split', { b: s.nBackfilled, l: s.nLive })
				]
					.filter(Boolean)
					.join(lang === 'en' ? ' ' : '')}
			</p>
		</section>

		<!-- (1b) Live only: signals pushed since launch, apart from the backfilled history. -->
		{#if live}
			<section class="mt-8 rounded-xl border border-border bg-card p-4 sm:p-5">
				<div class="flex flex-wrap items-center justify-between gap-2">
					<h2 class="text-lg font-semibold tracking-tight">{t(lang, 'record.live.title')}</h2>
					{@render sourceBadge(true)}
				</div>
				<p class="mt-1 text-sm text-muted-foreground">{t(lang, 'record.live.sub')}</p>
				{#if live.nSignals === 0}
					<p class="mt-3 text-sm text-foreground">{t(lang, 'record.live.none')}</p>
				{:else}
					<div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
						<Kpi
							label={t(lang, 'record.live.signals')}
							value={live.nSignals}
							sub={fmt('record.live.signalsSub', { c: live.nClosed, o: live.nOpen })}
						/>
						<Kpi
							label={t(lang, 'record.kpi.winRate')}
							value={winRate(live.winRate)}
							sub={live.nClosed
								? fmt('record.live.winRateSub', {
										n: live.nClosed,
										w: Math.round((live.winRate ?? 0) * live.nClosed)
									})
								: ''}
						/>
						<div class="col-span-2 sm:col-span-1">
							<Kpi
								label={t(lang, 'record.live.ret')}
								value={pct(live.ret)}
								sub={t(lang, 'record.live.retSub')}
								tone={live.ret == null ? 'default' : kpiTone(live.ret)}
							/>
						</div>
					</div>
					<p class="mt-3 text-xs text-muted-foreground">
						{live.firstEntry ? fmt('record.live.first', { ts: minute(live.firstEntry) }) : ''}
						{t(lang, 'record.live.method')}
					</p>
				{/if}
				{#if live.smallSample}
					<Callout type="warning">
						<p>{fmt('record.live.small', { n: live.nClosed, min: LIVE_MIN_SAMPLE })}</p>
					</Callout>
				{/if}
			</section>
		{/if}

		{#if $user}
			<MyFollows
				{lang}
				{follows}
				record={mine}
				status={mineStatus}
				{busyId}
				onUnfollow={toggleFollow}
			/>
		{/if}

		<!-- (2) Per-asset state: holding (entry → exit line) or waiting (distance to trigger). -->
		<section class="mt-10">
			<h2 class="text-lg font-semibold tracking-tight">{t(lang, 'record.assets.title')}</h2>
			<p class="mt-1 text-sm text-muted-foreground">{t(lang, 'record.assets.sub')}</p>
			<div class="mt-4 grid gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
				{#each record as r (r.asset)}
					{@const long = r.open_entry_ts != null}
					<article class="flex flex-col rounded-xl border border-border bg-card p-4 sm:p-5">
						<div class="flex items-center justify-between gap-3">
							<h3 class="text-lg font-bold">{r.asset}</h3>
							<StatusPill
								status={long ? 'long' : 'stopped'}
								label={t(lang, long ? 'record.state.long' : 'record.state.flat')}
							/>
						</div>
						<div class="mt-3 flex flex-col gap-2 text-[13px] sm:mt-4">
							{#if long}
								<div>
									{@render stat(t(lang, 'record.card.bought'), fmtPrice(r.open_entry_price))}
									<div
										class="mt-1 flex flex-wrap items-center justify-end gap-x-2 gap-y-1 text-[11px] text-muted-foreground"
									>
										<span class="bdv-num"
											>{fmt('record.card.boughtAt', { ts: minute(r.open_entry_ts) })}</span
										>
										{@render sourceBadge(r.open_live === true)}
									</div>
								</div>
								{@render stat(t(lang, 'record.card.last'), fmtPrice(r.last_close))}
								{@render stat(t(lang, 'record.card.openRet'), pct(r.open_ret), tone(r.open_ret))}
								<div>
									{@render stat(t(lang, 'record.card.exitLine'), fmtPrice(r.channel_low))}
									<div class="bdv-num mt-1 text-right text-[11px] text-muted-foreground">
										{fmt('record.card.fromLast', { pct: pct(dist(r.channel_low, r.last_close)) })}
									</div>
								</div>
							{:else}
								{@render stat(t(lang, 'record.card.last'), fmtPrice(r.last_close))}
								<div>
									{@render stat(t(lang, 'record.card.trigger'), fmtPrice(r.channel_high))}
									<div class="bdv-num mt-1 text-right text-[11px] text-muted-foreground">
										{fmt('record.card.fromLast', { pct: pct(dist(r.channel_high, r.last_close)) })}
									</div>
								</div>
							{/if}
						</div>
						<!-- Same sentence on every card: skip it on phones, where 13 stacked cards get long. -->
						<p class="mt-3 hidden text-xs text-muted-foreground sm:block">
							{t(lang, long ? 'record.card.exitHint' : 'record.card.triggerHint')}
						</p>
						<div class="mt-auto pt-3 sm:pt-4">
							<div
								class="flex flex-col gap-1 border-t border-border pt-3 text-xs text-muted-foreground"
							>
								{#if r.start_ts && r.sleeve_ret != null && r.hold_ret != null}
									<div class="bdv-eyebrow text-[10px]">
										{fmt('record.card.since', { start: day(r.start_ts) })}
									</div>
									<div>
										{t(lang, 'record.card.strategy')}
										<span class="bdv-num {tone(r.sleeve_ret)}">{pct(r.sleeve_ret)}</span>
										· {t(lang, 'record.card.hold')}
										<span class="bdv-num {tone(r.hold_ret)}">{pct(r.hold_ret)}</span>
									</div>
								{/if}
								<div>{fmt('record.card.stats', { n: r.n_closed, w: r.n_wins })}</div>
								{#if r.avg_win != null || r.avg_loss != null}
									<div>
										{fmt('record.card.avg', { win: pct(r.avg_win), loss: pct(r.avg_loss) })}
									</div>
								{/if}
							</div>
						</div>
					</article>
				{/each}
			</div>
		</section>
	{/if}

	<!-- (4) The rule in plain words, the fee assumption, the honest note, the disclaimer. -->
	<section class="mt-10">
		<div class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-lg font-semibold tracking-tight">{t(lang, 'record.rules.title')}</h2>
			<ul class="mt-3 flex list-disc flex-col gap-2 pl-5 text-sm text-muted-foreground">
				{#each RULE_KEYS as k (k)}
					<li>{t(lang, k)}</li>
				{/each}
			</ul>
			<a
				href={resolve('/method')}
				class="mt-3 inline-block text-sm font-medium text-primary hover:underline"
				>{t(lang, 'record.methodLink')}</a
			>
		</div>
		<div class="md:grid md:grid-cols-2 md:gap-x-4">
			<Callout type="warning" title={t(lang, 'record.honest.title')}>
				<p>{t(lang, 'record.honest.body')}</p>
				{#if s && s.winRate != null && s.best}
					<p class="mt-2">
						{fmt('record.honest.stats', {
							start: day(s.startTs),
							n: s.nClosed,
							w: s.nWins,
							rate: winRate(s.winRate),
							asset: s.best.asset,
							best: pct(s.best.ret)
						})}
					</p>
				{/if}
			</Callout>
			<Callout type="info" title={t(lang, 'record.backfill.title')}>
				<p>{t(lang, 'record.backfill.body')}</p>
				{#if s?.liveSince}
					<p class="mt-2">{fmt('record.backfill.since', { since: day(s.liveSince) })}</p>
				{/if}
			</Callout>
		</div>
		<p class="text-xs text-muted-foreground">⚠️ {t(lang, 'record.disclaimer')}</p>
	</section>

	<!-- CTA: the existing Telegram subscription card (topic strategy_signals). -->
	<section id="alerts" class="mt-10">
		<h2 class="text-lg font-semibold tracking-tight">{t(lang, 'record.cta.title')}</h2>
		<p class="mt-1 mb-4 text-sm text-muted-foreground">{t(lang, 'record.cta.sub')}</p>
		<AlertSubscribe />
	</section>

	<!-- (3) Full trade history, newest first. Cards below sm, a table from sm up. -->
	{#if trades.length}
		<section class="mt-10">
			<h2 class="text-lg font-semibold tracking-tight">{t(lang, 'record.trades.title')}</h2>
			<p class="mt-1 text-sm text-muted-foreground">
				{fmt('record.trades.sub', { n: trades.length })}
			</p>

			<ul
				class="mt-4 flex flex-col divide-y divide-border rounded-lg border border-border bg-card sm:hidden"
			>
				{#each shown as tr (tr.id)}
					{@const open = tr.exit_ts == null}
					{@const ret = open ? floating(tr) : tr.net_ret}
					<li class="px-3 py-2.5">
						<div class="flex items-center justify-between gap-2">
							<div class="flex items-center gap-2">
								<span class="font-semibold text-foreground">{tr.asset}</span>
								{@render sourceBadge(tr.live)}
							</div>
							<span class="bdv-num {tone(ret)}">
								{pct(ret)}
								{#if open}
									<span class="text-[10px] text-muted-foreground"
										>{t(lang, 'record.trades.floating')}</span
									>
								{/if}
							</span>
						</div>
						<div class="bdv-num mt-1 text-[11px] text-muted-foreground">
							{day(tr.entry_ts)} → {open ? t(lang, 'record.trades.holding') : day(tr.exit_ts)}
							· {heldDays(tr.hold_days)}
						</div>
						<div class="flex items-center justify-between gap-2">
							<div class="bdv-num text-[11px] text-muted-foreground">
								{fmtPrice(tr.entry_price)} → {open ? '—' : fmtPrice(tr.exit_price)}
							</div>
							{#if $user && tr.live}{@render followButton(tr)}{/if}
						</div>
					</li>
				{/each}
			</ul>

			<div class="mt-4 hidden overflow-x-auto rounded-lg border border-border sm:block">
				<table class="w-full text-left text-xs">
					<thead class="bg-secondary/50 text-muted-foreground">
						<tr>
							<th class="px-3 py-2">{t(lang, 'record.col.asset')}</th>
							<th class="px-3 py-2">{t(lang, 'record.col.entry')}</th>
							<th class="px-3 py-2">{t(lang, 'record.col.exit')}</th>
							<th class="px-3 py-2 text-right">{t(lang, 'record.col.ret')}</th>
							<th class="px-3 py-2 text-right">{t(lang, 'record.col.days')}</th>
							<th class="px-3 py-2">{t(lang, 'record.col.source')}</th>
							{#if $user}<th class="px-3 py-2">{t(lang, 'record.follow.col')}</th>{/if}
						</tr>
					</thead>
					<tbody>
						{#each shown as tr (tr.id)}
							{@const open = tr.exit_ts == null}
							{@const ret = open ? floating(tr) : tr.net_ret}
							<tr class="border-t border-border">
								<td class="px-3 py-2 font-semibold text-foreground">{tr.asset}</td>
								<td class="px-3 py-2">
									<div class="bdv-num text-foreground">{fmtPrice(tr.entry_price)}</div>
									<div class="bdv-num text-[11px] text-muted-foreground">{minute(tr.entry_ts)}</div>
								</td>
								<td class="px-3 py-2">
									{#if open}
										<StatusPill status="long" label={t(lang, 'record.trades.holding')} />
									{:else}
										<div class="bdv-num text-foreground">{fmtPrice(tr.exit_price)}</div>
										<div class="bdv-num text-[11px] text-muted-foreground">
											{minute(tr.exit_ts)}
										</div>
									{/if}
								</td>
								<td class="bdv-num px-3 py-2 text-right {tone(ret)}">
									{pct(ret)}
									{#if open}
										<div class="text-[10px] text-muted-foreground">
											{t(lang, 'record.trades.floating')}
										</div>
									{/if}
								</td>
								<td class="bdv-num px-3 py-2 text-right text-muted-foreground">
									{heldDays(tr.hold_days)}
								</td>
								<td class="px-3 py-2">{@render sourceBadge(tr.live)}</td>
								{#if $user}<td class="px-3 py-2">{@render followButton(tr)}</td>{/if}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>

			{#if trades.length > PREVIEW}
				<button
					type="button"
					onclick={() => (showAll = !showAll)}
					class="mt-3 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
				>
					{showAll
						? t(lang, 'record.trades.showLess')
						: fmt('record.trades.showAll', { n: trades.length })}
				</button>
			{/if}
		</section>
	{/if}
</main>
