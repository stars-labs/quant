// Telegram alert-subscription client — thin wrapper around api.telegram_links /
// api.telegram_links_rw (PostgREST). Mirrors backtests.ts. RLS scopes the read
// view to the current user. Binding itself happens out-of-band: the user opens
// the t.me deep link (TELEGRAM_BOT_URL?start=<link_token>) and presses START;
// an external dispatcher then flips `bound` — the UI just polls getMyLink().
import { CONFIG } from './config';
import { getToken } from './auth';
import type { MyFollow, MyFollowRecord } from './types';

// Valid quant.telegram_links topics (migrations 032/035): the house trend rule's buy/sell signals +
// weekly scorecard, smart-DCA boost days, the morning opportunity digest, US-equity paper trades.
export type TelegramTopic = 'strategy_signals' | 'dca_boost' | 'daily_scan' | 'equity_trades';

export interface TelegramLink {
	link_token: string;
	bound: boolean;
	topics: string[];
	/** House coins for strategy_signals entries/exits (migration 037): null = all, [] = none. */
	coins: string[] | null;
}

export const TELEGRAM_BOT_URL = 'https://t.me/freemanXbtc_bot';

function authHeaders(): HeadersInit {
	const t = getToken();
	if (!t) throw new Error('not authenticated');
	return {
		Authorization: `Bearer ${t}`,
		'Content-Type': 'application/json',
		Accept: 'application/json'
	};
}

/** The current user's link row (RLS scopes to them), or null if not created yet. */
export async function getMyLink(f: typeof fetch = fetch): Promise<TelegramLink | null> {
	const r = await f(`${CONFIG.API_BASE}/telegram_links?select=link_token,bound,topics,coins`, {
		headers: authHeaders()
	});
	if (!r.ok) throw new Error(`link ${r.status}`);
	return ((await r.json()) as TelegramLink[])[0] ?? null;
}

/** Create the user's link row. user_id must equal the JWT sub (RLS enforces it). */
export async function createLink(userId: string, f: typeof fetch = fetch): Promise<TelegramLink> {
	const r = await f(`${CONFIG.API_BASE}/telegram_links_rw`, {
		method: 'POST',
		headers: { ...authHeaders(), Prefer: 'return=representation' },
		body: JSON.stringify({ user_id: userId })
	});
	if (!r.ok) throw new Error(`create ${r.status}: ${await r.text().catch(() => '')}`.slice(0, 200));
	// The rw view returns {user_id, link_token, topics}; a fresh row is never bound.
	const row = ((await r.json()) as { link_token: string; topics: string[] | null }[])[0];
	return { link_token: row.link_token, bound: false, topics: row.topics ?? [], coins: null };
}

/** Replace the user's topic subscriptions. */
export async function updateTopics(
	userId: string,
	topics: string[],
	f: typeof fetch = fetch
): Promise<void> {
	const r = await f(`${CONFIG.API_BASE}/telegram_links_rw?user_id=eq.${userId}`, {
		method: 'PATCH',
		headers: authHeaders(),
		body: JSON.stringify({ topics })
	});
	if (!r.ok) throw new Error(`topics ${r.status}: ${await r.text().catch(() => '')}`.slice(0, 200));
}

/** Replace the user's coin filter for strategy_signals (null = all coins). */
export async function updateCoins(
	userId: string,
	coins: string[] | null,
	f: typeof fetch = fetch
): Promise<void> {
	const r = await f(`${CONFIG.API_BASE}/telegram_links_rw?user_id=eq.${userId}`, {
		method: 'PATCH',
		headers: authHeaders(),
		body: JSON.stringify({ coins })
	});
	if (!r.ok) throw new Error(`coins ${r.status}: ${await r.text().catch(() => '')}`.slice(0, 200));
}

// ── Follow ledger ("我跟了这笔", migration 037). Owner-only views: RLS / auth.uid() scope every
// read and write to the logged-in user. Only live (pushed) signals can be followed.

/** The user's followed trades, newest entry first. */
export async function getMyFollows(f: typeof fetch = fetch): Promise<MyFollow[]> {
	const r = await f(`${CONFIG.API_BASE}/my_follows`, { headers: authHeaders() });
	if (!r.ok) throw new Error(`follows ${r.status}`);
	return (await r.json()) as MyFollow[];
}

/** The user's follow record, or null before their first follow. */
export async function getMyFollowRecord(f: typeof fetch = fetch): Promise<MyFollowRecord | null> {
	const r = await f(`${CONFIG.API_BASE}/my_follow_record`, { headers: authHeaders() });
	if (!r.ok) throw new Error(`follow record ${r.status}`);
	return ((await r.json()) as MyFollowRecord[])[0] ?? null;
}

/** Mark a live trade as followed (user_id defaults to the JWT's uid). Already marked = ok. */
export async function followTrade(tradeId: number, f: typeof fetch = fetch): Promise<void> {
	const r = await f(`${CONFIG.API_BASE}/user_follows`, {
		method: 'POST',
		headers: { ...authHeaders(), Prefer: 'return=minimal' },
		body: JSON.stringify({ trade_id: tradeId })
	});
	if (!r.ok && r.status !== 409)
		throw new Error(`follow ${r.status}: ${await r.text().catch(() => '')}`.slice(0, 200));
}

/** Unmark a followed trade. */
export async function unfollowTrade(tradeId: number, f: typeof fetch = fetch): Promise<void> {
	const r = await f(`${CONFIG.API_BASE}/user_follows?trade_id=eq.${tradeId}`, {
		method: 'DELETE',
		headers: authHeaders()
	});
	if (!r.ok) throw new Error(`unfollow ${r.status}`);
}
