// Telegram alert-subscription client — thin wrapper around api.telegram_links /
// api.telegram_links_rw (PostgREST). Mirrors backtests.ts. RLS scopes the read
// view to the current user. Binding itself happens out-of-band: the user opens
// the t.me deep link (TELEGRAM_BOT_URL?start=<link_token>) and presses START;
// an external dispatcher then flips `bound` — the UI just polls getMyLink().
import { CONFIG } from './config';
import { getToken } from './auth';

// Valid quant.telegram_links topics (migration 032): the house trend rule's buy/sell signals +
// weekly scorecard, and US-equity paper trades.
export type TelegramTopic = 'strategy_signals' | 'equity_trades';

export interface TelegramLink {
	link_token: string;
	bound: boolean;
	topics: string[];
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
	const r = await f(`${CONFIG.API_BASE}/telegram_links?select=link_token,bound,topics`, {
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
	return { link_token: row.link_token, bound: false, topics: row.topics ?? [] };
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
