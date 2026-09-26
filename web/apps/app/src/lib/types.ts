// Shared row types for the public API (mirrors migration 002 + 007 views).

/** Aggregate snapshot exposed to anon via api.public_stats. */
export interface PublicStats {
	total_runs: number;
	total_trades: number;
	distinct_strategies: number;
	best_profit_pct: number | null;
	best_calmar: number | null;
	best_sharpe: number | null;
	best_sortino: number | null;
	best_win_rate: number | null;
	min_max_dd: number | null;
	last_updated: string;
}

export interface BacktestRun {
	id: number;
	job_id: string | null;
	strategy: string;
	timeframe: string | null;
	timerange: string | null;
	started_at: string | null;
	finished_at: string | null;
	duration_sec: number | null;
	total_trades: number | null;
	wins: number | null;
	losses: number | null;
	win_rate_pct: number | null;
	total_profit_pct: number | null;
	total_profit_abs: number | null;
	max_drawdown_pct: number | null;
	calmar: number | null;
	sharpe: number | null;
	sortino: number | null;
	profit_factor: number | null;
	pairs: string[] | null;
	factors: string[] | null;
	imported_at: string;
}

export interface BacktestTrade {
	run_id: number;
	trade_id: number;
	pair: string;
	is_short: boolean;
	open_date: string;
	close_date: string | null;
	open_rate: number | null;
	close_rate: number | null;
	stake_amount: number | null;
	profit_abs: number | null;
	profit_pct: number | null;
	exit_reason: string | null;
	enter_tag: string | null;
	trade_duration_min: number | null;
}

export interface OhlcRow {
	pair: string;
	bucket: string; // ISO ts
	open: number;
	high: number;
	low: number;
	close: number;
	volume: number;
}

export interface LiveTrade {
	bot_name: string;
	pair: string;
	is_short: boolean;
	strategy: string | null;
	open_date: string;
	close_date: string | null;
	open_rate: number | null;
	close_rate: number | null;
	stake_amount: number | null;
	profit_abs: number | null;
	profit_pct: number | null;
	exit_reason: string | null;
	synced_at: string;
}

// NautilusTrader execution-engine positions (api.nautilus_trades). Separate from freqtrade
// LiveTrade; `environment` is 'testnet' | 'live'.
export interface NautilusTrade {
	trader_id: string;
	strategy: string;
	instrument: string;
	venue: string;
	environment: string;
	asset_class: 'crypto' | 'equity';
	is_short: boolean;
	open_date: string;
	close_date: string | null;
	open_rate: number | null;
	close_rate: number | null;
	quantity: number | null;
	realized_pnl: number | null;
	profit_pct: number | null;
	exit_reason: string | null;
	synced_at: string;
}

// House trend rule, per asset (api.strategy_record, migration 032) — the single source of truth
// for every track-record stat. Returns are fractions, net of 0.1% fee per side; channel_high is
// the next bar's buy trigger, channel_low the next bar's exit line.
export interface StrategyRecord {
	strategy: string;
	asset: string;
	start_ts: string | null;
	start_price: number | null;
	last_ts: string | null;
	last_close: number | null;
	channel_high: number | null;
	channel_low: number | null;
	n_closed: number;
	n_wins: number;
	closed_compound: number;
	best_ret: number | null;
	avg_win: number | null;
	avg_loss: number | null;
	open_entry_ts: string | null;
	open_entry_price: number | null;
	open_live: boolean | null;
	open_ret: number | null;
	sleeve_ret: number | null;
	hold_ret: number | null;
}

// One house-rule trade (api.strategy_trades). live=false = backfilled (rule replayed on history
// after the fact), never a real-time call. net_ret is NULL while the trade is open.
export interface StrategyTrade {
	id: number;
	strategy: string;
	asset: string;
	entry_ts: string;
	entry_price: number;
	entry_level: number;
	exit_ts: string | null;
	exit_price: number | null;
	exit_level: number | null;
	live: boolean;
	created_at: string;
	net_ret: number | null;
	hold_days: number | null;
}

// A backtest of a CURRENTLY-DEPLOYED Nautilus strategy (honest numbers, not freqtrade).
export interface NautilusBacktest {
	id: number;
	engine: string;
	asset_class: 'crypto' | 'equity';
	strategy: string;
	label: string;
	instruments: string[] | null;
	timeframe: string | null;
	period_start: string | null;
	period_end: string | null;
	environment: string;
	total_trades: number | null;
	wins: number | null;
	losses: number | null;
	win_rate_pct: number | null;
	total_profit_pct: number | null;
	max_drawdown_pct: number | null;
	calmar: number | null;
	sharpe: number | null;
	sortino: number | null;
	params: Record<string, unknown> | null;
	run_at: string;
}

// NVDA-centric semiconductor supply-chain universe (real Yahoo data → /semis page).
export interface SemiTicker {
	symbol: string;
	name: string;
	tier: 'core' | 'upstream' | 'peer' | 'downstream' | 'benchmark';
	stage: string | null; // fine value-chain step (materials … hyperscaler)
	trends: string[] | null; // technology-trend tags (HBM, CoWoS, EUV, optical, VRM, …)
	role: string | null;
	market_cap: number | null;
	last_price: number | null;
	ret_1w: number | null;
	ret_1m: number | null;
	ret_3m: number | null;
	ret_6m: number | null;
	ret_1y: number | null;
	ret_ytd: number | null;
	rs_vs_nvda: number | null;
	rs_vs_smh: number | null;
	corr_nvda: number | null;
	beta_nvda: number | null;
	vol_annual: number | null;
	from_52w_high: number | null;
	mom_score: number | null;
	alpha_score: number | null;
	alpha_note: string | null;
	updated_at: string;
}

export interface SemiGroup {
	tier: string;
	members: number;
	avg_ret_1m: number | null;
	avg_ret_3m: number | null;
	avg_ret_1y: number | null;
	avg_corr_nvda: number | null;
	updated_at: string;
}

// System-level AI-server value-chain bottleneck matrix (api.semi_segments).
// Scores 1-5; seeded from docs/research/AI_HARDWARE_BOTTLENECK_MATRIX_2026.md.
export interface SemiSegment {
	id: number;
	segment: string; // en key
	segment_zh: string;
	bottleneck: number; // 瓶颈强度 1-5
	pricing_power: number; // 定价权 1-5
	sub_risk: number; // 技术替代风险 1-5
	note_zh: string; // 关键证据
	track_metric: string; // 读者跟踪指标
	tickers: string[]; // representative public tickers
	trend_tags: string[];
	status_2026: string | null; // verified current data point (null = open gap)
	source_url: string | null;
}

// Daily NetLiq snapshot of our own paper/testnet accounts (api.account_snapshots —
// public, the verifiable equity-curve artifact).
export interface AccountSnapshot {
	snap_date: string;
	account: string;
	asset_class: 'equity' | 'crypto';
	environment: string;
	net_liq: number;
	currency: string;
	ts: string;
}

export interface WfResult {
	id: number;
	run_date: string;
	strategy: string;
	timeframe: string;
	window_label: string;
	window_start: string;
	window_end: string;
	status: 'ok' | 'failed' | string;
	trades: number | null;
	tot_profit_pct: number | null;
	tot_profit_usdt: number | null;
	avg_profit_pct: number | null;
}

export interface EventDcaTrigger {
	ts: string;
	kind: 'FLASH' | 'FAST' | 'SUSTAIN' | 'CAPITUL' | string;
	price: number | null;
	severity: number | null;
	fng: number | null;
	amount_usdt: number | null;
	mode: string | null;
}

// Curated market-news headlines (quant.news_items — English originals, reposted verbatim)
export interface NewsItem {
	published_at: string;
	source: string;
	category: 'crypto' | 'macro' | 'equity' | 'global' | string;
	title: string;
	link: string;
}

// 市场压力指数 (api.market_stress) — explainable composite; components carries every
// input's raw value, 0-100 subscore and the mapping note (never a black box).
export interface MarketStress {
	ts: string;
	stress_score: number;
	label: '平静' | '正常' | '紧张' | '高压' | string;
	components: Record<string, { raw: number; score: number; note: string }>;
}

// Supabase-side events
export interface KolEvent {
	id: number;
	timestamp: string;
	kol: string;
	sentiment: string | null;
	score: number | null;
	title: string;
	source: string | null;
}

export interface HyperoptEpoch {
	id: string;
	strategy: string;
	file_ts: string;
	epoch: number;
	is_best: boolean | null;
	is_initial_point: boolean | null;
	is_random: boolean | null;
	loss: number | null;
	params: Record<string, number> | null;
	sharpe: number | null;
	calmar: number | null;
	sortino: number | null;
	sqn: number | null;
	profit_total: number | null;
	winrate: number | null;
	total_trades: number | null;
	max_drawdown: number | null;
	holding_avg_hours: number | null;
	results_explanation: string | null;
	synced_at: string;
}

export interface DcaLogRow {
	id: number;
	timestamp: string;
	mode: string;
	base_usdt: number;
	multiplier: number;
	amount_usdt: number;
	fng_value: number | null;
	cycle_score: number | null;
	cycle_signal: string | null;
	explain: Record<string, unknown> | null;
	order_result: unknown | null;
}

// Kelly sizing verdict — generated server-side by
// strategies/telegram_alerts.py --write-kelly-status. Refreshed on every
// daily-report run; the file lives at static/data/kelly_status.json.
export interface KellyStatusEntry {
	name: string;
	status: 'ok' | 'negative_edge' | 'insufficient_n' | 'no_data';
	verdict: string;
	win_rate?: number;
	payoff_ratio?: number;
	n_trades?: number;
	f_half_point?: number;
	f_half_shrunk?: number;
	// Backtest-level context (optional). Useful for surfacing "Kelly says
	// negative-edge but backtest made +X% over Y days" together so the user
	// sees the disagreement.
	profit_total_pct?: number;
	backtest_start?: string;
	backtest_end?: string;
	error?: string;
}

export interface KellyStatusFile {
	generated_at: string;
	min_trades_for_kelly: number;
	wilson_z: number;
	strategies: KellyStatusEntry[];
	error?: string;
}
