// Self-service backtest playground client — thin wrapper around api.backtest_jobs /
// api.backtest_results (PostgREST). Mirrors userPrefs.ts. Requires a valid JWT; RLS
// (auth.uid()) scopes everything to the current user. The runner (game box) executes
// queued jobs and writes results. See PLAYGROUND_PLAN.md + migrations/014.
import { CONFIG } from './config';
import { getToken } from './auth';

export type Strategy =
	'honest_trend' | 'accumulator' | 'donchian' | 'master_portfolio' | 'quant_lab';
export type JobStatus = 'queued' | 'running' | 'done' | 'error';

export interface BacktestJob {
	id: string;
	user_id: string;
	strategy: Strategy;
	params: Record<string, unknown>;
	status: JobStatus;
	error: string | null;
	created_at: string;
	updated_at: string;
}

// master_portfolio detail payloads (the runner emits both since 2026-06; legacy result
// rows lack them — the UI shows a "re-run for details" hint instead).
export interface PortfolioHolding {
	sym: string;
	units: number; // ETF shares held at the end (份额)
	value: number; // USD market value at the end
	weight_pct: number; // actual final weight — compare against the target in config.weights
}
export interface PortfolioTradeLeg {
	sym: string;
	w_before: number; // drifted weight before the trade (%)
	w_target: number; // target weight (%) — the whole reason for the trade
	delta_usd: number; // signed trade size: > 0 buy, < 0 sell
	price: number; // execution price used
	units_after: number; // shares held after the trade
}
export interface PortfolioTradeEvent {
	date: string; // ISO date of the rebalance bar
	kind: 'initial' | 'rebalance';
	total: number; // portfolio value on that date (USD)
	legs: PortfolioTradeLeg[];
}

export interface BacktestResult {
	job_id: string;
	user_id: string;
	metrics: {
		return_pct: number;
		max_dd_pct: number | null;
		sharpe: number | null;
		calmar: number | null;
		trades: number;
		// Data window the run actually covered (ISO dates). Legacy rows lack these.
		period_start?: string | null;
		period_end?: string | null;
		// master_portfolio only: final holdings + the full rebalance journal.
		holdings?: PortfolioHolding[];
		trade_log?: PortfolioTradeEvent[];
		// quant_lab only: model diagnostics rendered by /quant-lab.
		kind?: 'quant_lab' | string;
		model?: string;
		assets?: string[];
		summary?: QuantLabSummaryRow[];
		tables?: QuantLabTable[];
		notes?: string[];
		[k: string]: unknown;
	};
	equity_curve: number[] | null; // downsampled equity values (~80 pts) for a sparkline
	created_at: string;
}

export interface QuantLabSummaryRow {
	label: string;
	value: string | number | null;
	unit?: string;
}

export interface QuantLabTable {
	name: string;
	rows: Record<string, string | number | null>[];
}

// Predefined strategies + their param domains — keep in lockstep with backtest_runner.py.
// The UI renders forms from this; the runner re-validates server-side (never trust the client).
export const CRYPTO_ASSETS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'LINK'] as const;

// Commodity continuous futures (10y daily history, '1d' ONLY) — accepted by honest_trend
// backtests and the ema_cross/donchian_breakout signals. Suggestions for the UI; the
// runner/evaluator validate server-side (unknown symbols error / never fire).
export const COMMODITY_ASSETS = [
	{ sym: 'GC', zh: '黄金', en: 'Gold' },
	{ sym: 'SI', zh: '白银', en: 'Silver' },
	{ sym: 'CL', zh: '原油(WTI)', en: 'Crude WTI' },
	{ sym: 'BZ', zh: '布伦特原油', en: 'Brent' },
	{ sym: 'HG', zh: '铜', en: 'Copper' },
	{ sym: 'NG', zh: '天然气', en: 'NatGas' },
	{ sym: 'PL', zh: '铂金', en: 'Platinum' },
	{ sym: 'PA', zh: '钯金', en: 'Palladium' },
	{ sym: 'KT', zh: '咖啡', en: 'Coffee' },
	{ sym: 'ZW', zh: '小麦', en: 'Wheat' },
	{ sym: 'ZS', zh: '大豆', en: 'Soybeans' },
	{ sym: 'ZC', zh: '玉米', en: 'Corn' }
] as const;

// Master-portfolio preset display data. The weights are PUBLIC recipes (books/whitepapers) —
// unofficial replicas (非官方复刻); keep in lockstep with the runner's preset table.
export const PORTFOLIO_PRESETS = {
	all_weather: {
		zh: '全天候(桥水风格)',
		en: 'All Weather (Bridgewater-style)',
		weights: { SPY: 30, TLT: 40, IEF: 15, GLD: 7.5, DBC: 7.5 }
	},
	permanent: {
		zh: '永久组合(Harry Browne)',
		en: 'Permanent (Harry Browne)',
		weights: { SPY: 25, TLT: 25, GLD: 25, BIL: 25 }
	},
	sixty_forty: { zh: '经典 60/40', en: 'Classic 60/40', weights: { SPY: 60, TLT: 40 } },
	buffett_90_10: { zh: '巴菲特 90/10', en: 'Buffett 90/10', weights: { SPY: 90, BIL: 10 } },
	golden_butterfly: {
		zh: '金蝴蝶',
		en: 'Golden Butterfly',
		weights: { SPY: 20, IWN: 20, TLT: 20, SHY: 20, GLD: 20 }
	}
} as const;
export type PortfolioPresetKey = keyof typeof PORTFOLIO_PRESETS;

// ETF → asset-class label for the weight chips ('SPY 美股大盘 30%').
export const PORTFOLIO_COMPONENTS: Record<string, readonly [zh: string, en: string]> = {
	SPY: ['美股大盘', 'US equities'],
	TLT: ['长期美债', 'Long-term Treasuries'],
	IEF: ['中期美债', 'Intermediate Treasuries'],
	GLD: ['黄金', 'Gold'],
	DBC: ['商品', 'Commodities'],
	BIL: ['现金类', 'Cash-like'],
	SHY: ['短债', 'Short-term Treasuries'],
	IWN: ['小盘价值', 'Small-cap value']
};

// Display metadata per strategy (plain-language layer — keys/params are the runner contract
// and stay unchanged): `name` is the 白话名, `tech` the technical label, `explain` a one-
// paragraph honest description, `paramHints` one-liners rendered under each param input.
export const STRATEGIES = {
	honest_trend: {
		label: 'HonestTrend (US equity)',
		name: ['美股趋势跟随', 'US trend following'] as const,
		tech: 'HonestTrend',
		explain: [
			'均线金叉买入、死叉卖出,顺势而为。涨势里拿得住,震荡市会反复止损。适合验证"长期趋势"想法。',
			'Buy the golden cross, sell the death cross. Rides trends; chops sideways. For testing long-trend ideas.'
		] as const,
		paramHints: {
			ema_fast: [
				'短期均线长度 — 越小越灵敏、信号越多',
				'short EMA length — smaller = more sensitive'
			],
			ema_slow: ['长期均线长度 — 定义"趋势"的尺度', 'long EMA — defines the trend scale']
		},
		blurb: [
			'EMA 金叉/死叉趋势跟随，支持任意美股代码及商品（黄金/原油等，日线 10 年历史），NVDA/AMD/QQQ 另有小时线',
			'EMA cross trend-following — any US ticker plus commodities (gold/oil etc., 10y daily history); hourly for NVDA/AMD/QQQ'
		] as const,
		// `assets` are SUGGESTIONS only — anyUsSymbol opens the field to any US ticker;
		// COMMODITY_ASSETS adds continuous futures. The runner validates against its ~9.5k
		// US-symbol list + the commodity set server-side; hourly bars exist only for the
		// suggested trio, everything else is daily.
		assets: ['NVDA', 'AMD', 'QQQ'],
		anyUsSymbol: true,
		note: [
			'非目录股票及商品（黄金/原油等）仅支持日线（10 年历史）',
			'Non-catalog tickers and commodities (gold/oil etc.): daily only (10y history)'
		] as const,
		timeframes: ['1h', '1d'],
		params: {
			ema_fast: { min: 5, max: 400, default: 50 },
			ema_slow: { min: 5, max: 400, default: 100 }
		}
	},
	// Donchian breakout — crypto trend, real Binance 1h bars. Honest equity-curve maxDD.
	donchian: {
		label: 'Donchian breakout (crypto trend)',
		name: ['突破追涨', 'Breakout'] as const,
		tech: 'Donchian breakout',
		explain: [
			'价格创出过去 N 根 K 线的新高就买入,跌破过去 M 根的新低就卖出。趋势行情吃肉,震荡行情挨打 —— 用回测看它在这个币上到底行不行。',
			'Buy fresh N-bar highs, exit on M-bar lows. Feasts in trends, bleeds in chop — backtest tells you which.'
		] as const,
		paramHints: {
			entry_lb: [
				'突破窗口:过去多少根 K 线的最高点算"新高"(168 根 1h ≈ 7 天)',
				'breakout window in bars (168×1h ≈ 7 days)'
			],
			exit_lb: ['离场窗口:跌破多少根 K 线的最低点就卖', 'exit window in bars'],
			risk_frac: ['每次入场动用资金的比例', 'fraction of equity per entry']
		},
		blurb: [
			'唐奇安通道突破做多，真实币安 1h K 线，诚实净值回撤',
			'Donchian channel breakout long, real Binance 1h bars, honest drawdown'
		] as const,
		assets: CRYPTO_ASSETS,
		timeframes: ['1h'],
		params: {
			entry_lb: { min: 12, max: 1000, default: 168 }, // breakout lookback (1h bars)
			exit_lb: { min: 6, max: 1000, default: 72 }, // trailing-low exit lookback; must be <= entry_lb
			risk_frac: { min: 0.01, max: 1, default: 0.2, step: 0.01 } // equity fraction deployed per entry
		}
	},
	// Low-buying smart DCA — crypto majors run on the Nautilus engine (FNG smart boost);
	// commodities + any US ticker run on the generic daily engine (smart = double the buy
	// when close < 200d SMA). Always '1d'. Never sells, so return_pct is ROI on invested
	// capital; max_dd/sharpe/calmar are null (round-trip metrics N/A).
	accumulator: {
		label: 'Smart DCA accumulator',
		name: ['恐慌加仓定投', 'Fear-boosted DCA'] as const,
		tech: 'Smart DCA',
		explain: [
			'固定周期买入。smart 模式低位加倍 —— 加密看恐惧贪婪指数,商品/美股看是否跌破 200 日均线。只买不卖,赌的是长期向上。',
			'Scheduled buys. Smart mode doubles at the lows — crypto reads the Fear & Greed index, commodities/US stocks check a close below the 200-day SMA. Never sells; bets on long-term upside.'
		] as const,
		paramHints: {
			base_buy_usd: ['每次定投金额', 'USD per buy'],
			interval_bars: ['每隔多少天买一次', 'days between buys'],
			mode: [
				'smart=低位加倍(币:恐慌;商品/美股:跌破200日线) / naive=固定金额',
				'smart = double at lows (crypto: fear; commodities/stocks: below 200d SMA) / naive = fixed'
			]
		},
		blurb: [
			'定投，越跌越买，只买不卖 —— 加密按恐慌加倍，黄金/美股按 200 日均线加倍',
			'DCA that buys more at the lows, never sells — crypto doubles on fear, gold/US stocks double below the 200d SMA'
		] as const,
		// Suggestions only — anyAsset opens the field to any commodity sym (GC/SI/CL/…)
		// or US ticker; the runner validates server-side.
		assets: CRYPTO_ASSETS,
		anyAsset: true,
		timeframes: ['1d'],
		params: {
			base_buy_usd: { min: 10, max: 100000, default: 500 }, // USD per scheduled buy
			interval_bars: { min: 1, max: 90, default: 7 }, // days between buys (1d bars)
			mode: { choices: ['smart', 'naive'], default: 'smart' } // smart = fear+dip boosted
		}
	},
	// Hedge-fund-style fixed-weight allocations (All Weather / Permanent / 60-40 / 90-10 /
	// Golden Butterfly). Multi-asset daily — no asset/tf params (noAsset); results carry
	// config.weights + cagr_pct, and `trades` is the rebalance count.
	master_portfolio: {
		label: 'Master portfolios (asset allocation)',
		name: ['大师组合复刻', 'Master allocations'] as const,
		tech: 'Asset Allocation',
		explain: [
			'把钱按固定比例分到股/债/金/商品,定期再平衡。桥水全天候等大师配方的公开版本复刻(非官方)。它不追求暴利 —— 看点是回撤:2022 股债双杀这种年份谁还活着。',
			'Fixed weights across stocks/bonds/gold/commodities, rebalanced periodically. Unofficial replicas of public recipes; the point is drawdown behavior, not moonshots.'
		] as const,
		paramHints: {
			preset: ['选一个公开配方,下方显示权重', 'pick a public recipe'],
			rebalance_months: ['每隔几个月把比例调回目标(1/3/12)', 'months between rebalances']
		},
		blurb: [
			'全天候、永久组合、60/40 等公开配方的忠实复刻 —— 不择时,赚"资产互补"的钱',
			'Faithful replicas of public allocation recipes — no timing, diversification does the work'
		] as const,
		noAsset: true, // portfolio is multi-asset daily — the form hides asset/tf controls
		params: {
			preset: {
				choices: ['all_weather', 'permanent', 'sixty_forty', 'buffett_90_10', 'golden_butterfly'],
				default: 'all_weather'
			},
			rebalance_months: { choices: ['1', '3', '12'], default: '3' }
		}
	}
} as const;

function authHeaders(): HeadersInit {
	const t = getToken();
	if (!t) throw new Error('not authenticated');
	return {
		Authorization: `Bearer ${t}`,
		'Content-Type': 'application/json',
		Accept: 'application/json'
	};
}

/**
 * Enqueue a backtest. user_id must equal the JWT sub (RLS enforces it). Returns the queued job.
 * params may include period_years: 1|2|3|5 to limit the data window — omit the key entirely
 * for full history (the runner treats absence as "all available data").
 */
export async function submitBacktest(
	strategy: Strategy,
	params: Record<string, unknown>,
	userId: string,
	f: typeof fetch = fetch
): Promise<BacktestJob> {
	const r = await f(`${CONFIG.API_BASE}/backtest_jobs`, {
		method: 'POST',
		headers: { ...authHeaders(), Prefer: 'return=representation' },
		body: JSON.stringify({ user_id: userId, strategy, params, status: 'queued' })
	});
	if (!r.ok) throw new Error(`submit ${r.status}: ${await r.text().catch(() => '')}`.slice(0, 200));
	return ((await r.json()) as BacktestJob[])[0];
}

/** The current user's jobs, newest first (RLS scopes to them). */
export async function myJobs(f: typeof fetch = fetch, strategy?: Strategy): Promise<BacktestJob[]> {
	const filter = strategy ? `&strategy=eq.${encodeURIComponent(strategy)}` : '';
	const r = await f(
		`${CONFIG.API_BASE}/backtest_jobs?select=*&order=created_at.desc&limit=50${filter}`,
		{
			headers: authHeaders()
		}
	);
	if (!r.ok) throw new Error(`jobs ${r.status}`);
	return (await r.json()) as BacktestJob[];
}

/** Result for one job, or null if not finished yet. */
export async function jobResult(
	jobId: string,
	f: typeof fetch = fetch
): Promise<BacktestResult | null> {
	const r = await f(`${CONFIG.API_BASE}/backtest_results?job_id=eq.${jobId}&select=*`, {
		headers: authHeaders()
	});
	if (!r.ok) throw new Error(`result ${r.status}`);
	return ((await r.json()) as BacktestResult[])[0] ?? null;
}
