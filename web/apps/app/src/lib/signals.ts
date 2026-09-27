// User-defined signal client — thin wrapper around api.user_signals /
// api.user_signals_rw / api.signal_fires (PostgREST). Mirrors backtests.ts.
// RLS (auth.uid()) scopes everything to the current user. A server-side
// evaluator watches bars, fires matching signals, and pushes to Telegram via
// the existing alert-subscribe binding. The server caps 10 active signals per
// user (the INSERT raises — we surface its error text).
import { writable } from 'svelte/store';
import { CONFIG } from './config';
import { getToken } from './auth';
import { COMMODITY_ASSETS } from './backtests';

// Commodity continuous futures (single source of truth: backtests.ts) — ema_cross /
// donchian_breakout accept them at 1d only; the evaluator never fires unknown symbols.
export { COMMODITY_ASSETS };

export type SignalKind = 'ema_cross' | 'donchian_breakout' | 'fng_threshold' | 'vix_threshold';
export type SignalStatus = 'active' | 'paused';

export interface UserSignal {
	id: string;
	user_id: string;
	name: string;
	kind: SignalKind;
	asset: string; // '*' for market-wide kinds (fng_threshold)
	timeframe: string;
	params: Record<string, unknown>;
	status: SignalStatus;
	last_fired_at: string | null;
	created_at: string;
}

export interface SignalFire {
	id: string;
	signal_id: string;
	user_id: string;
	fired_at: string;
	bar_ts: string | null;
	details: { message?: string; price?: number; direction?: string; [k: string]: unknown };
	signal_name: string | null;
}

/** Insert payload — id is GENERATED server-side, never send it. */
export interface NewSignal {
	user_id: string;
	name: string;
	kind: SignalKind;
	asset: string;
	timeframe: string;
	params: Record<string, unknown>;
}

// Kinds + their param domains — mirror the backtest strategies (backtests.ts
// STRATEGIES). The UI renders forms from this; the evaluator re-validates
// server-side (never trust the client).
export const CRYPTO_ASSETS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'LINK'] as const;
// Core 3 + the semi-universe chain (matches quant.semi_universe — the evaluator's allowed set).
export const EQUITY_ASSETS = [
	'NVDA',
	'AMD',
	'QQQ',
	'SPY',
	'SMH',
	'MSFT',
	'GOOGL',
	'META',
	'AMZN',
	'AVGO',
	'TSM',
	'ASML',
	'AMAT',
	'LRCX',
	'KLAC',
	'MU',
	'INTC',
	'QCOM',
	'TXN',
	'ARM',
	'MRVL',
	'ANET',
	'SMCI',
	'DELL',
	'HPE',
	'ORCL',
	'COHR',
	'CDNS',
	'SNPS',
	'TER',
	'ENTG',
	'GFS',
	'UMC',
	'ASX',
	'AMKR',
	'CRDO',
	'MKSI',
	'DD',
	'LIN'
] as const;

export const SIGNAL_KINDS = {
	ema_cross: {
		label: ['EMA 金叉死叉', 'EMA golden/death cross'] as const,
		params: {
			ema_fast: { min: 2, max: 400, default: 20 },
			ema_slow: { min: 3, max: 400, default: 50 },
			direction: { choices: ['golden', 'death', 'both'], default: 'both' }
		}
	},
	donchian_breakout: {
		label: ['唐奇安突破', 'Donchian breakout'] as const,
		params: {
			entry_lb: { min: 12, max: 1000, default: 168 },
			exit_lb: { min: 6, max: 1000, default: 72 },
			side: { choices: ['entry', 'exit', 'both'], default: 'both' }
		}
	},
	// Market-wide Fear & Greed threshold — no asset/timeframe choice (always '*' / '1d').
	fng_threshold: {
		label: ['恐惧贪婪阈值 (加密)', 'Fear & Greed threshold (crypto)'] as const,
		params: {
			below: { min: 1, max: 99, default: 25 }
		}
	},
	// Market-wide VIX fear threshold — the US-equity counterpart of FNG (always '*' / '1d').
	vix_threshold: {
		label: ['VIX 恐慌阈值 (美股)', 'VIX fear threshold (US equity)'] as const,
		params: {
			above: { min: 10, max: 80, default: 25 }
		}
	}
} as const;

export function isEquityAsset(a: string): boolean {
	return (EQUITY_ASSETS as readonly string[]).includes(a);
}

export function isCryptoAsset(a: string): boolean {
	return (CRYPTO_ASSETS as readonly string[]).includes(a);
}

export function isCommodityAsset(a: string): boolean {
	return COMMODITY_ASSETS.some((c) => c.sym === a);
}

/**
 * Allowed timeframes for a kind+asset: crypto majors get 1h or 1d; commodities
 * (continuous futures) are 1d only; anything else (EQUITY_ASSETS or any free-text
 * alphanumeric ticker — assumed US equity) is 1d only; FNG/VIX fixed 1d. The
 * evaluator skips symbols it can't resolve server-side.
 */
export function timeframesFor(kind: SignalKind, asset: string): string[] {
	if (kind === 'fng_threshold' || kind === 'vix_threshold') return ['1d'];
	if (isCommodityAsset(asset)) return ['1d'];
	return isCryptoAsset(asset) ? ['1h', '1d'] : ['1d'];
}

/** Bump to make <MySignals /> re-fetch (e.g. after creating a signal from a backtest row). */
export const signalsVersion = writable(0);

function authHeaders(): HeadersInit {
	const t = getToken();
	if (!t) throw new Error('not authenticated');
	return {
		Authorization: `Bearer ${t}`,
		'Content-Type': 'application/json',
		Accept: 'application/json'
	};
}

// PostgREST errors are JSON {message,...} — surface the message (e.g. the
// 10-active-signals cap raised by the INSERT trigger) instead of raw JSON.
async function errText(r: Response, op: string): Promise<string> {
	const t = await r.text().catch(() => '');
	let msg = t;
	try {
		msg = (JSON.parse(t) as { message?: string }).message ?? t;
	} catch {
		// not JSON — keep the raw body
	}
	return `${op} ${r.status}: ${msg}`.slice(0, 200);
}

/** The current user's signals, newest first (RLS scopes to them). */
export async function mySignals(f: typeof fetch = fetch): Promise<UserSignal[]> {
	const r = await f(`${CONFIG.API_BASE}/user_signals?select=*&order=created_at.desc`, {
		headers: authHeaders()
	});
	if (!r.ok) throw new Error(`signals ${r.status}`);
	return (await r.json()) as UserSignal[];
}

/** Create a signal. user_id must equal the JWT sub (RLS enforces it). Returns the new row. */
export async function createSignal(input: NewSignal, f: typeof fetch = fetch): Promise<UserSignal> {
	const r = await f(`${CONFIG.API_BASE}/user_signals_rw`, {
		method: 'POST',
		headers: { ...authHeaders(), Prefer: 'return=representation' },
		body: JSON.stringify(input)
	});
	if (!r.ok) throw new Error(await errText(r, 'create'));
	return ((await r.json()) as UserSignal[])[0];
}

/** Pause or resume one signal. */
export async function setSignalStatus(
	id: string,
	status: SignalStatus,
	f: typeof fetch = fetch
): Promise<void> {
	const r = await f(`${CONFIG.API_BASE}/user_signals_rw?id=eq.${id}`, {
		method: 'PATCH',
		headers: authHeaders(),
		body: JSON.stringify({ status })
	});
	if (!r.ok) throw new Error(await errText(r, 'status'));
}

/** Delete one signal (its fire history rows stay server-side per schema). */
export async function deleteSignal(id: string, f: typeof fetch = fetch): Promise<void> {
	const r = await f(`${CONFIG.API_BASE}/user_signals_rw?id=eq.${id}`, {
		method: 'DELETE',
		headers: authHeaders()
	});
	if (!r.ok) throw new Error(await errText(r, 'delete'));
}

/** The current user's recent fires, newest first. */
export async function myFires(f: typeof fetch = fetch): Promise<SignalFire[]> {
	const r = await f(`${CONFIG.API_BASE}/signal_fires?select=*&order=fired_at.desc&limit=50`, {
		headers: authHeaders()
	});
	if (!r.ok) throw new Error(`fires ${r.status}`);
	return (await r.json()) as SignalFire[];
}
