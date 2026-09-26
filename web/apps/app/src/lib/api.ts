// Unified data client — works in browser AND SvelteKit server (load / +server).
// Fetch is passed in explicitly so we can leverage SvelteKit's wrapped fetch
// during SSR (caching + relative URLs + cookie forwarding).
import { CONFIG } from './config';
import type {
	BacktestRun,
	BacktestTrade,
	OhlcRow,
	LiveTrade,
	NautilusTrade,
	WfResult,
	EventDcaTrigger,
	HyperoptEpoch,
	KolEvent,
	DcaLogRow,
	PublicStats,
	NautilusBacktest,
	SemiTicker,
	SemiGroup,
	SemiSegment,
	AccountSnapshot,
	NewsItem,
	MarketStress,
	StrategyRecord,
	StrategyTrade
} from './types';
import { getToken } from './auth';

type Fetch = typeof fetch;
type Params = Record<string, string | number>;
/** Per-call auth override. Pass `Bearer <jwt>` from server loads (cookie);
 * in the browser the default `vpsAuth()` reads localStorage. */
type WithAuth = { authHeader?: string };

async function req<T>(
	base: string,
	path: string,
	params?: Params,
	f: Fetch = fetch,
	extraHeaders?: HeadersInit
): Promise<T> {
	const url = new URL(path, base);
	if (params) for (const [k, v] of Object.entries(params)) url.searchParams.set(k, String(v));
	const headers: HeadersInit = { Accept: 'application/json', ...extraHeaders };
	const r = await f(url.toString(), { headers });
	if (!r.ok) {
		const body = await r.text().catch(() => '');
		throw Object.assign(new Error(`${r.status} ${url.pathname} ${body.slice(0, 120)}`), {
			status: r.status
		});
	}
	return r.json() as Promise<T>;
}

// --- VPS PostgREST ---
function vpsAuth(explicit?: string): HeadersInit {
	if (explicit) return { Authorization: explicit };
	const t = getToken();
	return t ? { Authorization: `Bearer ${t}` } : {};
}

export const vps = {
	// ---- public-preview endpoints (anon-accessible) ----
	publicStats: (f: Fetch = fetch) => req<PublicStats[]>(CONFIG.API_BASE, '/public_stats', {}, f),

	// Honest current numbers: aggregates over quant.nautilus_backtests (re-run on Nautilus),
	// NOT the retired freqtrade backtest_runs. Same shape as PublicStats (superset).
	nautilusStats: (f: Fetch = fetch) =>
		req<PublicStats[]>(CONFIG.API_BASE, '/nautilus_stats', {}, f),

	nautilusBacktests: (f: Fetch = fetch) =>
		req<NautilusBacktest[]>(CONFIG.API_BASE, '/nautilus_backtests', {}, f),

	// NVDA-centric semiconductor supply-chain analysis (real Yahoo data).
	semiUniverse: (f: Fetch = fetch) =>
		req<SemiTicker[]>(CONFIG.API_BASE, '/semi_universe', { order: 'ret_3m.desc.nullslast' }, f),
	semiGroups: (f: Fetch = fetch) => req<SemiGroup[]>(CONFIG.API_BASE, '/semi_groups', {}, f),
	// System-level AI-server value-chain bottleneck matrix (HBM/CoWoS/substrate/MLCC/VRM/cooling/…).
	semiSegments: (f: Fetch = fetch) =>
		req<SemiSegment[]>(CONFIG.API_BASE, '/semi_segments', { order: 'id.asc' }, f),

	// Daily NetLiq snapshots of our own paper/testnet accounts (public — the verifiable
	// equity-curve artifact; see migration 022 + strategies/account_snapshot.py).
	accountSnapshots: (f: Fetch = fetch) =>
		req<AccountSnapshot[]>(CONFIG.API_BASE, '/account_snapshots', { order: 'snap_date.asc' }, f),

	publicOhlcDaily: (
		f: Fetch = fetch,
		pair: string,
		{ from, to, limit = 3000 }: { from?: string; to?: string; limit?: number } = {}
	) => {
		const params: Params = { pair: `eq.${pair}`, order: 'bucket.asc', limit };
		if (from) params.bucket = `gte.${from}`;
		if (to) params.and = `(bucket.lt.${to})`;
		return req<OhlcRow[]>(CONFIG.API_BASE, '/public_ohlc_1d', params, f);
	},

	// Curated news headlines (anon-accessible; sources: CoinDesk/The Block/… = crypto,
	// Fed/SEC/ECB = macro, MarketWatch/CNBC = equity). Reposted verbatim, never rewritten.
	newsItems: (
		f: Fetch = fetch,
		{ category, limit = 120 }: { category?: string; limit?: number } = {}
	) => {
		const params: Params = { order: 'published_at.desc', limit };
		if (category) params.category = `eq.${category}`;
		return req<NewsItem[]>(CONFIG.API_BASE, '/news_items', params, f);
	},

	// 市场压力指数 — hourly explainable composite (anon-accessible; view is ts DESC,
	// 90-day window). limit=1 → latest reading; larger limit → recent history.
	marketStress: (f: Fetch = fetch, { limit = 1 }: { limit?: number } = {}) =>
		req<MarketStress[]>(CONFIG.API_BASE, '/market_stress', { limit }, f),

	// House trend-rule track record (anon-accessible; migration 032). strategy_record is the
	// single source of truth for every stat — consumers only average across its rows.
	strategyRecord: (f: Fetch = fetch) =>
		req<StrategyRecord[]>(CONFIG.API_BASE, '/strategy_record', { order: 'asset.asc' }, f),
	strategyTrades: (f: Fetch = fetch, { limit = 1000 }: { limit?: number } = {}) =>
		req<StrategyTrade[]>(CONFIG.API_BASE, '/strategy_trades', { order: 'entry_ts.desc', limit }, f),

	publicEventTriggers: (f: Fetch = fetch, { limit = 500 }: { limit?: number } = {}) =>
		req<EventDcaTrigger[]>(
			CONFIG.API_BASE,
			'/public_event_triggers',
			{ order: 'ts.desc', limit },
			f
		),

	// ---- authenticated endpoints (anon 401) ----
	backtestRuns: (
		f: Fetch = fetch,
		{ strategy, limit = 100, authHeader }: { strategy?: string; limit?: number } & WithAuth = {}
	) => {
		const params: Params = { order: 'started_at.desc.nullslast', limit };
		if (strategy) params.strategy = `eq.${strategy}`;
		return req<BacktestRun[]>(CONFIG.API_BASE, '/backtest_runs', params, f, vpsAuth(authHeader));
	},

	backtestTrades: (
		f: Fetch = fetch,
		runId: number,
		{ limit = 10000, authHeader }: { limit?: number } & WithAuth = {}
	) =>
		req<BacktestTrade[]>(
			CONFIG.API_BASE,
			'/backtest_trades',
			{ run_id: `eq.${runId}`, order: 'open_date.asc', limit },
			f,
			vpsAuth(authHeader)
		),

	ohlcDaily: (
		f: Fetch = fetch,
		pair: string,
		{
			from,
			to,
			limit = 3000,
			authHeader
		}: { from?: string; to?: string; limit?: number } & WithAuth = {}
	) => {
		const params: Params = { pair: `eq.${pair}`, order: 'bucket.asc', limit };
		if (from) params.bucket = `gte.${from}`;
		if (to) params.and = `(bucket.lt.${to})`;
		return req<OhlcRow[]>(CONFIG.API_BASE, '/ohlc_1d', params, f, vpsAuth(authHeader));
	},

	ohlcHourly: (
		f: Fetch = fetch,
		pair: string,
		{
			from,
			to,
			limit = 3000,
			authHeader
		}: { from?: string; to?: string; limit?: number } & WithAuth = {}
	) => {
		const params: Params = { pair: `eq.${pair}`, order: 'bucket.asc', limit };
		if (from) params.bucket = `gte.${from}`;
		if (to) params.and = `(bucket.lt.${to})`;
		return req<OhlcRow[]>(CONFIG.API_BASE, '/ohlc_1h_recent', params, f, vpsAuth(authHeader));
	},

	ohlc15m: (
		f: Fetch = fetch,
		pair: string,
		{
			from,
			to,
			limit = 3000,
			authHeader
		}: { from?: string; to?: string; limit?: number } & WithAuth = {}
	) => {
		const params: Params = { pair: `eq.${pair}`, order: 'bucket.asc', limit };
		if (from) params.bucket = `gte.${from}`;
		if (to) params.and = `(bucket.lt.${to})`;
		return req<OhlcRow[]>(CONFIG.API_BASE, '/ohlc_15m_recent', params, f, vpsAuth(authHeader));
	},

	/** Auto-granularity for OHLC — server picks the right aggregate. */
	async ohlcAuto(
		f: Fetch,
		pair: string,
		{
			from,
			to,
			maxPoints = 2000,
			authHeader
		}: { from: Date; to: Date; maxPoints?: number } & WithAuth
	): Promise<{ rows: OhlcRow[]; source: string }> {
		const spanMin = (to.getTime() - from.getTime()) / 60_000;
		const target = spanMin / maxPoints;
		const p = { from: from.toISOString(), to: to.toISOString(), limit: maxPoints, authHeader };
		if (target <= 30) return { rows: await this.ohlc15m(f, pair, p), source: 'ohlc_15m_recent' };
		if (target <= 300) return { rows: await this.ohlcHourly(f, pair, p), source: 'ohlc_1h_recent' };
		return { rows: await this.ohlcDaily(f, pair, p), source: 'ohlc_1d' };
	},

	liveTrades: (
		f: Fetch = fetch,
		{ bot, limit = 100, authHeader }: { bot?: string; limit?: number } & WithAuth = {}
	) => {
		const params: Params = { order: 'open_date.desc', limit };
		if (bot) params.bot_name = `eq.${bot}`;
		return req<LiveTrade[]>(CONFIG.API_BASE, '/live_trades', params, f, vpsAuth(authHeader));
	},

	// NautilusTrader execution-engine positions (separate from freqtrade live_trades).
	nautilusTrades: (
		f: Fetch = fetch,
		{
			environment,
			assetClass,
			limit = 100,
			authHeader
		}: { environment?: string; assetClass?: 'crypto' | 'equity'; limit?: number } & WithAuth = {}
	) => {
		const params: Params = { order: 'open_date.desc', limit };
		if (environment) params.environment = `eq.${environment}`;
		if (assetClass) params.asset_class = `eq.${assetClass}`;
		return req<NautilusTrade[]>(
			CONFIG.API_BASE,
			'/nautilus_trades',
			params,
			f,
			vpsAuth(authHeader)
		);
	},

	walkForward: (
		f: Fetch = fetch,
		{ strategy, limit = 200, authHeader }: { strategy?: string; limit?: number } & WithAuth = {}
	) => {
		const params: Params = { order: 'run_date.desc,window_label.asc', limit };
		if (strategy) params.strategy = `eq.${strategy}`;
		return req<WfResult[]>(CONFIG.API_BASE, '/wf_results', params, f, vpsAuth(authHeader));
	},

	eventDcaTriggers: (
		f: Fetch = fetch,
		{ limit = 100, authHeader }: { limit?: number } & WithAuth = {}
	) =>
		req<EventDcaTrigger[]>(
			CONFIG.API_BASE,
			'/event_dca_triggers',
			{ order: 'ts.desc', limit },
			f,
			vpsAuth(authHeader)
		),

	hyperoptEpochs: (
		f: Fetch = fetch,
		{
			strategy,
			limit = 500,
			onlyBest = false,
			authHeader
		}: { strategy?: string; limit?: number; onlyBest?: boolean } & WithAuth = {}
	) => {
		const params: Params = { order: 'loss.asc', limit };
		if (strategy) params.strategy = `eq.${strategy}`;
		if (onlyBest) params.is_best = 'eq.true';
		return req<HyperoptEpoch[]>(
			CONFIG.API_BASE,
			'/hyperopt_epochs',
			params,
			f,
			vpsAuth(authHeader)
		);
	}
};

// --- Supabase cloud ---
function sbHeaders(): HeadersInit {
	return {
		apikey: CONFIG.SUPABASE_ANON,
		Authorization: `Bearer ${CONFIG.SUPABASE_ANON}`
	};
}

export const supabase = {
	kolEvents: (f: Fetch = fetch, { limit = 100 }: { limit?: number } = {}) =>
		req<KolEvent[]>(
			CONFIG.SUPABASE_URL,
			'/rest/v1/kol_events',
			{ order: 'timestamp.desc', limit },
			f,
			sbHeaders()
		),
	dcaLog: (f: Fetch = fetch, { limit = 100 }: { limit?: number } = {}) =>
		req<DcaLogRow[]>(
			CONFIG.SUPABASE_URL,
			'/rest/v1/dca_log',
			{ order: 'timestamp.desc', limit },
			f,
			sbHeaders()
		)
};
