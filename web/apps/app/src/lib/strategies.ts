// Strategy catalog — prose + static metadata for each strategy name in
// quant.backtest_runs. Numeric metrics stay in the DB; this file covers only
// what-does-it-do / which-assets / where-to-read-more. Keys must match the
// `strategy` column exactly.
//
// Prose fields are { zh, en } pairs. Use pickStrategy(meta, lang) to get a
// flattened view for a template.

import type { Lang } from './i18n';

export interface L {
	zh: string;
	en: string;
}
export interface LArr {
	zh: string[];
	en: string[];
}

export interface StrategyMeta {
	name: string;
	tagline: L;
	mode: 'spot' | 'futures' | 'hybrid';
	assets: string[];
	timeframe: string;
	summary: L;
	/** Ordered bullets explaining the core loop. Rendered as a list. */
	mechanics: LArr;
	/** Relative links to plotly reports under /reports/. */
	reports: { label: L; path: string }[];
	/** Docs slug under /docs/strategies/. */
	docSlug?: string;
	status: 'live' | 'dryrun' | 'research' | 'retired';
}

export interface FlatStrategy {
	name: string;
	tagline: string;
	mode: StrategyMeta['mode'];
	assets: string[];
	timeframe: string;
	summary: string;
	mechanics: string[];
	reports: { label: string; path: string }[];
	docSlug?: string;
	status: StrategyMeta['status'];
}

const META: StrategyMeta[] = [
	{
		name: 'HonestTrend15mDry',
		tagline: {
			zh: '基线策略：BTC/ETH/BNB/SOL 现货 15m EMA 交叉 + ADX',
			en: 'Baseline 15m EMA-cross + ADX on BTC/ETH/BNB/SOL spot'
		},
		mode: 'spot',
		assets: ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT'],
		timeframe: '15m',
		summary: {
			zh: '诚实的基线：纯现货做多，EMA 快慢线交叉+ADX 强度确认，20% 回撤硬熔断。没有骚操作、没有杠杆、没有手工干预 —— 这是所有其他策略必须打败的基准线。',
			en: 'The honest baseline: long-only spot, EMA fast/slow cross confirmed by ADX strength, 20% drawdown kill-switch. No tricks, no leverage, no overrides — this is the bar every other strategy must beat.'
		},
		mechanics: {
			zh: [
				'入场：EMA(快) 上穿 EMA(慢) 且 ADX > 阈值',
				'出场：EMA 反向交叉 或 ROI 表 或 硬止损',
				'风控：账户级回撤 20% → RETIRE（不恢复）',
				'仓位：单次进场（不加仓、不 DCA）'
			],
			en: [
				'Entry: EMA(fast) crosses above EMA(slow) AND ADX > threshold',
				'Exit: EMA cross back OR ROI table OR hard stoploss',
				'Risk: 20% account-level drawdown → RETIRE (no resume)',
				'Position: single-shot (no scaling, no DCA)'
			]
		},
		reports: [
			{
				label: { zh: '全历史 BTC/ETH', en: 'Full-history BTC/ETH' },
				path: '/reports/full_history_btceth/'
			}
		],
		docSlug: 'honest-trend-report',
		status: 'dryrun'
	},
	{
		name: 'HonestTrend15mAdvanced',
		tagline: {
			zh: '基线 + Freqtrade Protections 插件',
			en: 'Baseline + Freqtrade Protections plugins'
		},
		mode: 'spot',
		assets: ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT'],
		timeframe: '15m',
		summary: {
			zh: '入场/出场与基线一致，但挂上 Freqtrade Protections：StoplossGuard、MaxDrawdown、CooldownPeriod。抓病态行情（例如持续震荡）时暂停策略，而不是继续流血。',
			en: 'Same entry/exit as the baseline, but with Freqtrade Protections active: StoplossGuard, MaxDrawdown, CooldownPeriod. Catches pathological runs (e.g. chopping in a range) and pauses the strategy instead of bleeding.'
		},
		mechanics: {
			zh: [
				'继承全部基线规则',
				'StoplossGuard：某个 pair 连续 N 次止损后暂停交易该 pair',
				'MaxDrawdownProtection：DD 超阈值后全局冷却',
				'CooldownPeriod：每次亏损交易强制休息'
			],
			en: [
				'All baseline rules',
				'StoplossGuard: stop trading on a pair after N consecutive stop-losses',
				'MaxDrawdownProtection: global cooldown after DD breaches threshold',
				'CooldownPeriod: force rest after every losing trade'
			]
		},
		reports: [
			{
				label: { zh: '全历史 BTC/ETH', en: 'Full-history BTC/ETH' },
				path: '/reports/full_history_btceth/'
			}
		],
		docSlug: 'honest-trend-report',
		status: 'dryrun'
	},
	{
		name: 'HonestTrend15mProtections',
		tagline: {
			zh: 'Protections + 自定义追踪止损',
			en: 'Protections + custom trailing stoploss'
		},
		mode: 'spot',
		assets: ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT'],
		timeframe: '15m',
		summary: {
			zh: '额外加入 custom_stoploss() 回调，根据 regime 松紧动态追踪利润。高 ADX 趋势收紧（锁定盈利）；震荡行情放松（避免被扫）。',
			en: 'Adds a custom_stoploss() callback that trails profit with regime-aware tightness. Tighter trail in high-ADX moves (protect the win); looser trail in ranging tape (avoid premature exits).'
		},
		mechanics: {
			zh: [
				'继承 Advanced 全部规则',
				'custom_stoploss() 基于 trade.open_rate * (1 + trail_pct) 计算动态止损',
				'利润 ≥ X ATR 后追踪收紧',
				'低流动性 regime 回退到硬止损'
			],
			en: [
				'All Advanced rules',
				'custom_stoploss() computes a dynamic SL anchored at trade.open_rate * (1 + trail_pct)',
				'Trail tightens once profit ≥ X ATR',
				'Falls back to hard SL in low-liquidity regimes'
			]
		},
		reports: [
			{
				label: { zh: '全历史 BTC/ETH', en: 'Full-history BTC/ETH' },
				path: '/reports/full_history_btceth/'
			}
		],
		docSlug: 'honest-trend-report',
		status: 'research'
	},
	{
		name: 'HonestTrend15mPyramid',
		tagline: {
			zh: '趋势 + 事件 DCA 加仓',
			en: 'Trend + event-DCA position scaling'
		},
		mode: 'spot',
		assets: ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT'],
		timeframe: '15m',
		summary: {
			zh: '首腿按常规趋势信号开仓，随后 adjust_trade_position() 在严重度加权的闪崩上加仓。确认上涨 regime 才金字塔；震荡不加。',
			en: 'Opens a first leg on the usual trend signal, then adjust_trade_position() adds paired legs on severity-scored flash dumps. Pyramiding down in a confirmed uptrend; no pyramid in sideways regimes.'
		},
		mechanics: {
			zh: [
				'第 1 腿：基线 EMA × ADX 入场',
				'第 2–4 腿：严重度加权 DCA（回撤幅度 × ADX 仍为正）',
				'腿数被 max_open_trades 限制；单次趋势翻转清掉所有腿',
				'与 Smart DCA event daemon 共享风险预算（不重复开火）'
			],
			en: [
				'Leg 1: baseline EMA×ADX entry',
				'Leg 2-4: severity-weighted DCA (drawdown × ADX-still-positive)',
				'Leg N capped by max_open_trades; exits all legs on a single trend flip',
				'Shares risk budget with Smart DCA event daemon (no double-fire)'
			]
		},
		reports: [
			{
				label: { zh: '金字塔 BTC/ETH', en: 'Pyramid BTC/ETH' },
				path: '/reports/full_history_btceth_pyramid/'
			},
			{ label: { zh: '金字塔研究', en: 'Pyramid research' }, path: '/reports/pyramid/' }
		],
		docSlug: 'honest-trend-report',
		status: 'research'
	},
	{
		name: 'HonestTrend1mLive',
		tagline: {
			zh: '1 分钟 scalp 变种（live 执行焦点）',
			en: '1-minute scalp variant (live execution focus)'
		},
		mode: 'spot',
		assets: ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'],
		timeframe: '1m',
		summary: {
			zh: '更快周期、同样逻辑 —— 用来验证执行路径（滑点、成交、timer jitter），不依赖 15m 信号的 P&L。即使盈利边际，做 live 基础设施演习很有用。',
			en: 'Faster timeframe, same logic — designed to validate the execution path (slippage, fills, timer jitter) without relying on the 15m signal. Useful as a live-infra shake-out even if its P&L is marginal.'
		},
		mechanics: {
			zh: [
				'1m K 线上跑基线 EMA×ADX',
				'更紧的 ROI / 止损（反复震荡的盘面）',
				'当作 live 实战演习，不是盈利核心'
			],
			en: [
				'Baseline EMA×ADX on 1m candles',
				'Tighter ROI / stoploss (whipsaw-dominant tape)',
				'Intended as a live-wire test, not a profit centre'
			]
		},
		reports: [],
		status: 'dryrun'
	},
	{
		name: 'HonestTrend1mMTF',
		tagline: {
			zh: '1m 入场、15m 高时间框架趋势守门',
			en: '1m entries gated by 15m higher-timeframe trend'
		},
		mode: 'spot',
		assets: ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'],
		timeframe: '1m',
		summary: {
			zh: '入场仍在 1m K 线，但只在 15m 的 informative 认同高周期趋势时开火。过滤掉逆大周期的 scalp 信号。',
			en: 'Entries still fire on the 1m candle but only when the 15m informative says the higher-timeframe trend agrees. Filters out scalp signals that fight the macro trend.'
		},
		mechanics: {
			zh: [
				'Informative DataFrame：15m EMA 方向 + ADX 强度',
				'1m 入场需要 15m.ema_dir > 0 且 15m.adx > 阈值',
				'出场用 1m EMA 交叉（比 HTF 门反应更快）'
			],
			en: [
				'Informative DataFrame: 15m EMA direction + ADX strength',
				'1m entry requires 15m.ema_dir > 0 AND 15m.adx > threshold',
				'Exit uses 1m EMA cross (faster reaction than the HTF gate)'
			]
		},
		reports: [],
		status: 'research'
	},
	{
		name: 'HonestTrendFutures',
		tagline: {
			zh: 'USDT-M 永续对冲：FnG + funding 过滤的空头趋势',
			en: 'USDT-M perpetual hedge: short-side trend with FnG + funding filter'
		},
		mode: 'futures',
		assets: ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT'],
		timeframe: '15m',
		summary: {
			zh: '与现货多头并行运行。趋势翻转且 Fear&Greed 高（市场贪婪）且 funding 为正（多头付溢价）时做空。目标是回撤缓冲，不是独立的盈利中心。',
			en: 'Runs in parallel with spot longs. Short when trend flips AND Fear&Greed is high (crowd euphoric) AND funding is positive (longs paying premium). Designed as a drawdown damper, not a standalone profit centre.'
		},
		mechanics: {
			zh: [
				'做空入场：EMA 下翻 且 FnG ≥ 70 且 funding > 0',
				'平空：趋势反转 或 FnG ≤ 40',
				'仓位低于现货（对冲比例，不是 1:1）',
				'Funding 成本纳入单笔 P&L —— 高 funding regime 自然少做空'
			],
			en: [
				'Short entry: EMA flip-down AND FnG ≥ 70 AND funding > 0',
				'Covers on trend flip-back OR FnG ≤ 40',
				'Lower position size vs spot (hedge ratio, not 1:1)',
				'Funding cost baked into per-trade P&L — high-funding regimes = fewer shorts'
			]
		},
		reports: [],
		docSlug: 'phase-b-futures-short',
		status: 'research'
	},
	{
		name: 'LiveProveIt',
		tagline: {
			zh: 'Production-gate 策略：只信 live 确认过的信号',
			en: 'Production-gate strategy: only live-confirmed signals'
		},
		mode: 'spot',
		assets: ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT'],
		timeframe: '15m',
		summary: {
			zh: '信号面和基线一致，但加了 live-telemetry 门：只有在历史窗口里 live 出现过且过 N 根 K 线没被 invalidate 的信号才开火。过滤"回测好看但 paper trade 做不出来"的伪信号。',
			en: 'Same signal surface as baseline but gated on a live-telemetry signal: trades only fire if the signal was seen live in a past window AND survived N bars without invalidation. Removes "looks good in backtest" signals that never paper-trade clean.'
		},
		mechanics: {
			zh: [
				'信号先经过 dry-run 日志',
				'维持 N 根 K 线后解锁入场',
				'信号失效立即释放，避免 trade-through'
			],
			en: [
				'Signal passes through a dry-run journal first',
				'Entry unlocked after N bars of signal persistence',
				'Quick-release on rejection to avoid trade-through'
			]
		},
		reports: [],
		status: 'research'
	}
];

export const STRATEGIES = META;

export function getStrategyMeta(name: string): StrategyMeta | null {
	return META.find((s) => s.name === name) ?? null;
}

export function pickStrategy(meta: StrategyMeta, lang: Lang): FlatStrategy {
	const p = <T>(f: { zh: T; en: T }) => (lang === 'en' ? f.en : f.zh);
	return {
		name: meta.name,
		tagline: p(meta.tagline),
		mode: meta.mode,
		assets: meta.assets,
		timeframe: meta.timeframe,
		summary: p(meta.summary),
		mechanics: p(meta.mechanics),
		reports: meta.reports.map((r) => ({ label: p(r.label), path: r.path })),
		docSlug: meta.docSlug,
		status: meta.status
	};
}

/** Tag chip class per factor — maps factor family to a BearDawnVerse
 * brand hue. Single shared `bdv-tag` rule handles bg/border via color-mix
 * on currentColor, so each variant only sets the foreground hue and gets
 * matching tinted bg + border for free. Auto-retunes in light mode. */
export function factorColor(tag: string): string {
	const base = 'bdv-tag';
	const map: Record<string, string> = {
		EMA: `${base} bdv-tag-indicator`,
		ADX: `${base} bdv-tag-indicator`,
		MACD: `${base} bdv-tag-indicator`,
		RSI: `${base} bdv-tag-indicator`,
		FnG: `${base} bdv-tag-macro`,
		Funding: `${base} bdv-tag-macro`,
		HTF: `${base} bdv-tag-macro`,
		Pyramid: `${base} bdv-tag-position`,
		DCA: `${base} bdv-tag-position`,
		Trailing: `${base} bdv-tag-position`,
		Protections: `${base} bdv-tag-position`,
		'DD-Kill': `${base} bdv-tag-risk`,
		Cooldown: `${base} bdv-tag-risk`,
		Spot: `${base} bdv-tag-spot`,
		'Futures-Short': `${base} bdv-tag-futures`,
		'Futures-L+S': `${base} bdv-tag-futures`,
		'Production-gate': `${base} bdv-tag-prod`,
		unknown: 'bg-muted text-muted-foreground border-border'
	};
	return map[tag] ?? 'bg-muted text-muted-foreground border-border';
}
