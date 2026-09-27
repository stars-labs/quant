<script lang="ts">
	// 我的跟单 — the logged-in user's own follow record (api.my_follows / api.my_follow_record,
	// migration 037; owner-only). Every number comes from those views; this only formats them.
	// Honest framing: signal prices + fees, not the user's real fills.
	import type { MyFollow, MyFollowRecord } from '$lib/types';
	import { t, type Lang } from '$lib/i18n';
	import { fmtPct, fmtPrice } from '$lib/utils';
	import Kpi from '$lib/components/kpi.svelte';

	interface Props {
		lang: Lang;
		follows: MyFollow[];
		record: MyFollowRecord | null;
		status: 'loading' | 'ready' | 'error';
		busyId: number | null;
		onUnfollow: (tradeId: number) => void;
	}
	let { lang, follows, record, status, busyId, onUnfollow }: Props = $props();

	function fmt(key: string, vars: Record<string, string | number>) {
		let out = t(lang, key);
		for (const [k, v] of Object.entries(vars)) out = out.replaceAll(`{${k}}`, String(v));
		return out;
	}
	const pct = (v: number | null | undefined) => (v == null ? '—' : fmtPct(v * 100, 1));
	const day = (ts: string | null) => (ts ? new Date(ts).toISOString().slice(0, 10) : '—');
	const tone = (v: number | null | undefined) =>
		v == null || v === 0
			? 'text-muted-foreground'
			: v > 0
				? 'text-[var(--profit)]'
				: 'text-[var(--loss)]';
	const kpiTone = (v: number) => (v > 0 ? 'good' : v < 0 ? 'bad' : 'default');
</script>

<section id="mine" class="mt-10 scroll-mt-20">
	<h2 class="text-lg font-semibold tracking-tight">{t(lang, 'record.mine.title')}</h2>
	<p class="mt-1 text-sm text-muted-foreground">{t(lang, 'record.mine.sub')}</p>

	{#if status === 'loading'}
		<p class="mt-4 text-sm text-muted-foreground">{t(lang, 'record.mine.loading')}</p>
	{:else if status === 'error'}
		<p class="mt-4 text-sm text-[var(--loss)]">{t(lang, 'record.mine.error')}</p>
	{:else if !record || record.n_followed === 0}
		<div class="mt-4 rounded-xl border border-dashed border-border bg-card p-5 text-sm">
			<p class="text-muted-foreground">{t(lang, 'record.mine.empty')}</p>
		</div>
	{:else}
		<div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
			<Kpi
				label={t(lang, 'record.mine.followed')}
				value={record.n_followed}
				sub={fmt('record.mine.followedSub', { c: record.n_closed, o: record.n_open })}
			/>
			<Kpi
				label={t(lang, 'record.kpi.winRate')}
				value={record.n_closed ? `${Math.round((record.n_wins / record.n_closed) * 100)}%` : '—'}
				sub={record.n_closed
					? fmt('record.mine.winRateSub', { n: record.n_closed, w: record.n_wins })
					: ''}
			/>
			<div class="col-span-2 sm:col-span-1">
				<Kpi
					label={t(lang, 'record.mine.ret')}
					value={record.n_closed ? pct(record.closed_compound) : '—'}
					sub={t(lang, 'record.mine.retSub')}
					tone={record.n_closed ? kpiTone(record.closed_compound) : 'default'}
				/>
			</div>
		</div>

		<ul class="mt-4 flex flex-col divide-y divide-border rounded-lg border border-border bg-card">
			{#each follows as f (f.trade_id)}
				{@const open = f.exit_ts == null}
				{@const ret = open ? f.open_ret : f.net_ret}
				<li class="flex items-center justify-between gap-3 px-3 py-2.5 text-sm">
					<div class="min-w-0">
						<div class="flex items-center gap-2">
							<span class="font-semibold text-foreground">{f.asset}</span>
							<span class="bdv-num {tone(ret)}">{pct(ret)}</span>
							{#if open}
								<span class="text-[10px] text-muted-foreground"
									>{t(lang, 'record.trades.floating')}</span
								>
							{/if}
						</div>
						<div class="bdv-num mt-0.5 text-[11px] text-muted-foreground">
							{day(f.entry_ts)}
							{fmtPrice(f.entry_price)} →
							{open
								? t(lang, 'record.trades.holding')
								: `${day(f.exit_ts)} ${fmtPrice(f.exit_price)}`}
						</div>
					</div>
					<button
						type="button"
						disabled={busyId != null}
						onclick={() => onUnfollow(f.trade_id)}
						class="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
						>{t(lang, 'record.follow.unmark')}</button
					>
				</li>
			{/each}
		</ul>
		<p class="mt-3 text-xs text-muted-foreground">{t(lang, 'record.mine.note')}</p>
		<p class="mt-1 text-xs text-muted-foreground">{t(lang, 'record.mine.tg')}</p>
	{/if}
</section>
