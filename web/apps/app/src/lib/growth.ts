// Pure helpers behind the growth loop (migration 037): ?ref= attribution, per-coin
// Telegram subscriptions and the live-only record. No imports, so `node --test` can run
// growth.test.ts directly: node --test src/lib/growth.test.ts

/** The house coin universe — mirrors strategies/strategy_record.py ASSETS (same order). */
export const HOUSE_COINS = [
	'BTC',
	'ETH',
	'SOL',
	'XRP',
	'DOGE',
	'ADA',
	'AVAX',
	'SUI',
	'NEAR',
	'UNI',
	'ZEC',
	'PEPE',
	'WLD'
] as const;

/** Same shape as the web_events_campaign_chk constraint. */
export const REF_RE = /^[a-z0-9_]{1,32}$/;

/** A valid ?ref= value from a query string (lower-cased), or null. */
export function refFromSearch(search: string): string | null {
	const r = new URLSearchParams(search).get('ref')?.toLowerCase() ?? '';
	return REF_RE.test(r) ? r : null;
}

/** Is `coin` selected? telegram_links.coins: null = every coin. */
export function hasCoin(coins: string[] | null, coin: string): boolean {
	return coins == null || coins.includes(coin);
}

/**
 * Toggle one coin. Returns the new telegram_links.coins value: null when every house coin
 * ends up selected (so coins added to the universe later are included automatically),
 * otherwise the selection in HOUSE_COINS order ([] = none).
 */
export function toggleCoin(coins: string[] | null, coin: string): string[] | null {
	const on = new Set<string>(coins ?? HOUSE_COINS);
	if (on.has(coin)) on.delete(coin);
	else on.add(coin);
	const next = HOUSE_COINS.filter((c) => on.has(c));
	return next.length === HOUSE_COINS.length ? null : next;
}

/** Below this many closed live trades the live block says the sample is still small. */
export const LIVE_MIN_SAMPLE = 20;

export interface LiveRecordRow {
	n_signals: number;
	n_closed: number;
	n_wins: number;
	n_open: number;
	closed_compound: number;
	first_entry_ts: string | null;
}

export interface LiveSummary {
	nSignals: number;
	nClosed: number;
	nOpen: number;
	winRate: number | null;
	ret: number | null;
	firstEntry: string | null;
	smallSample: boolean;
}

/** api.strategy_live_record (one row per strategy, none before the first live signal). */
export function liveSummary(row: LiveRecordRow | null | undefined): LiveSummary {
	const nClosed = row?.n_closed ?? 0;
	return {
		nSignals: row?.n_signals ?? 0,
		nClosed,
		nOpen: row?.n_open ?? 0,
		winRate: nClosed > 0 ? (row!.n_wins ?? 0) / nClosed : null,
		ret: nClosed > 0 ? (row!.closed_compound ?? 0) : null,
		firstEntry: row?.first_entry_ts ?? null,
		smallSample: nClosed < LIVE_MIN_SAMPLE
	};
}
