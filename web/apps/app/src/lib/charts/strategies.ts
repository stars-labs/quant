// Bilingual descriptions of each tradable strategy in the system.
// Used by <StrategyInfo strategy="HonestTrend15mDry" /> popovers across
// /strategies, /strategies/[name], /signals, and the home leaderboard
// so beginners can click the ⓘ next to a strategy name and learn what it
// actually does without leaving the page.
//
// Adding a new strategy? Provide entries in both `zh` and `en`. Keep
// `pitch` to one short sentence — it's the marquee line of the popover.

export type StrategyCopy = {
	name: string;
	pitch: string; // One-line elevator pitch
	philosophy: string; // Why this strategy exists / what edge it tries to capture
	factors: string[]; // Factor tags ("EMA-cross", "ADX", "Pyramid", …)
	bestFor: string; // Market regimes / pairs / horizons it does well in
	worstFor: string; // Where it gets eaten alive
	risk?: string; // Optional notes on risk profile / drawdown character
};

export type StrategyEntry = {
	zh: StrategyCopy;
	en: StrategyCopy;
};

export const STRATEGIES: Record<string, StrategyEntry> = {
	HonestTrend15mDry: {
		zh: {
			name: 'HonestTrend15mDry',
			pitch: '15 分钟级 EMA 交叉趋势跟随，BTC/ETH/BNB/SOL 现货，dry-run 验证版本。',
			philosophy: '主流币的中频趋势策略 — EMA(72) 上穿 EMA(144) + ADX(18) 确认趋势强度才入场，避开横盘震荡里被噪音洗。最简洁的"趋势 + 过滤器"组合。',
			factors: ['EMA-cross', 'ADX', '最小持仓 12h', 'F&G > 80 禁入', 'Spot only'],
			bestFor: '主流币明确趋势市 (单边上涨或单边下跌的延续段)。',
			worstFor: '横盘震荡市 — EMA 反复假突破，连续假信号会消耗本金。',
			risk: '基本无固定止损 (stoploss=-99%)，靠出场信号 + 时间止损控制风险。回测最大回撤 ~10–15%。'
		},
		en: {
			name: 'HonestTrend15mDry',
			pitch: '15-minute EMA-crossover trend follower on BTC/ETH/BNB/SOL spot — dry-run validation build.',
			philosophy: 'Mid-frequency trend strategy on majors — fast EMA(72) crossing slow EMA(144) plus ADX(18) confirmation only enters when momentum is real, avoiding chop. The clean "trend + filter" pattern.',
			factors: ['EMA-cross', 'ADX', 'min hold 12h', 'block when F&G > 80', 'Spot only'],
			bestFor: 'Majors in a clearly trending regime (sustained directional moves).',
			worstFor: 'Sideways chop — EMA generates fakeouts and consecutive false signals bleed capital.',
			risk: 'No hard stoploss (-99%); relies on exit signals + min-hold timer. Backtest max drawdown ~10–15%.'
		}
	},

	HonestTrend15mPyramid: {
		zh: {
			name: 'HonestTrend15mPyramid',
			pitch: 'HonestTrend15mDry 的加仓版本 — 趋势确认后只对赢家加仓 2 次。',
			philosophy: '"Pyramid winners, never Martingale" — 浮盈到一定阈值才加仓，亏损永不加仓。回测显示比单笔入场多 +41% 利润，最大回撤却没涨。',
			factors: ['EMA-cross', 'ADX', 'Pyramid 加仓 2 次', '只加赢家', '最小持仓 12h', 'Spot'],
			bestFor: '强趋势行情 — 单根大阳/大阴的延续段，加仓能放大盈利。',
			worstFor: '虚假突破后回踩 — 加仓位置被反向洗出会比单笔入场亏更多。',
			risk: '回测 Calmar 通常比 Dry 版本高 20–40%，但也更依赖趋势的"质量"。'
		},
		en: {
			name: 'HonestTrend15mPyramid',
			pitch: 'HonestTrend15mDry plus pyramid scaling — only winners get 2 add-ons.',
			philosophy: '"Pyramid winners, never Martingale" — only adds to a position once it’s already in profit by a threshold; never averages down. Backtest shows +41% extra profit vs single-entry with the same max drawdown.',
			factors: ['EMA-cross', 'ADX', 'Pyramid (+2 entries)', 'winners only', 'min hold 12h', 'Spot'],
			bestFor: 'Strong trending tape — sustained directional candles where stacking compounds gains.',
			worstFor: 'Fake breakout + retest — added entries get washed out at worse prices than the original.',
			risk: 'Calmar typically 20–40% higher than the Dry version, but more dependent on trend quality.'
		}
	},

	HonestTrend15mProtections: {
		zh: {
			name: 'HonestTrend15mProtections',
			pitch: 'HonestTrend15mDry + 一组保护规则 — 触发任意保护就停一段时间。',
			philosophy: '即使是好策略，连续亏损段也会摧毁信心。Protections (cooldown / 最大DD守护 / 低效交易冷却) 在该停手时强制停手，让策略"主动休息"。',
			factors: ['EMA-cross', 'ADX', 'Cooldown', 'MaxDrawdown', 'StoplossGuard', 'LowProfitPairs'],
			bestFor: '想"无人值守"地长期跑 — 保护规则替你处理异常段。',
			worstFor: '高频抓快进快出 — 每次保护触发都会错过几小时的机会。'
		},
		en: {
			name: 'HonestTrend15mProtections',
			pitch: 'HonestTrend15mDry plus a guard layer — any protection trips and the strategy benches itself.',
			philosophy: 'Even good strategies have consecutive-loss spells that break trader confidence. Protections (cooldown / max-DD guard / low-profit pair pause) force the strategy to step aside when conditions degrade.',
			factors: ['EMA-cross', 'ADX', 'Cooldown', 'MaxDrawdown', 'StoplossGuard', 'LowProfitPairs'],
			bestFor: 'Hands-off long-running deployment — the guards handle anomalies for you.',
			worstFor: 'Fast in/out scalping — every protection trip benches you for hours of missed entries.'
		}
	},

	HonestTrend15mAdvanced: {
		zh: {
			name: 'HonestTrend15mAdvanced',
			pitch: 'HonestTrend 家族的"全开版"— Pyramid + Protections + custom_stoploss + 自定义出场逻辑全部启用。',
			philosophy: '把所有能装的过滤器和增强机制都堆在一起。最复杂、研究阶段最深，但也最容易过拟合 — Walk-Forward 一致性是关键评估指标。',
			factors: ['EMA-cross', 'ADX', 'Pyramid', 'Protections', 'CustomStoploss', 'TrailingExit', 'F&G filter'],
			bestFor: '资金量较大需要精细管理 — 每个组件都在分担一类风险。',
			worstFor: '小资金 / 高频测试 — 复杂度高，参数交互多，难调试。',
			risk: '过拟合风险最高的版本，必须配合 walk-forward 验证使用。'
		},
		en: {
			name: 'HonestTrend15mAdvanced',
			pitch: 'The "everything on" build — Pyramid + Protections + custom_stoploss + custom exit logic all stacked.',
			philosophy: 'Every filter and enhancement the framework supports, layered on top of each other. Most complex and most thoroughly researched, but also the easiest to over-fit — walk-forward consistency is the critical signal.',
			factors: ['EMA-cross', 'ADX', 'Pyramid', 'Protections', 'CustomStoploss', 'TrailingExit', 'F&G filter'],
			bestFor: 'Larger capital that needs fine-grained risk management — each piece handles a different risk class.',
			worstFor: 'Small capital / fast iteration — too many interacting parameters, hard to debug.',
			risk: 'The highest over-fit risk variant; must be validated by walk-forward before any live capital.'
		}
	},

	HonestTrend1mLive: {
		zh: {
			name: 'HonestTrend1mLive',
			pitch: '1 分钟级 EMA 交叉，"已经在跑实盘"的高频版本。',
			philosophy: '把同一套趋势逻辑搬到 1m，参数自然更小 (EMA fast/slow 缩比)。胜率比 15m 高，但单笔利润小、对手续费极敏感 — 必须确认费率 < 0.05%。',
			factors: ['EMA-cross', 'ADX', '1m TF', 'Spot', '高频高胜率'],
			bestFor: '小资金、低费率账户做"刷分"。日内多次开平。',
			worstFor: '高费率交易所 / 滑点严重的小币 — 边际容易被费用吞噬。'
		},
		en: {
			name: 'HonestTrend1mLive',
			pitch: '1-minute EMA-crossover — the live-running high-frequency variant.',
			philosophy: 'Same trend logic on a 1-minute timeframe with proportionally smaller EMA windows. Higher win rate than the 15m version, but tiny per-trade profit and extremely fee-sensitive — only viable when fees < 0.05%.',
			factors: ['EMA-cross', 'ADX', '1m TF', 'Spot', 'high-freq high-WR'],
			bestFor: 'Small accounts on low-fee exchanges, multiple intraday cycles.',
			worstFor: 'High-fee venues or thin altcoins where slippage devours the edge.'
		}
	},

	HonestTrendFutures: {
		zh: {
			name: 'HonestTrendFutures',
			pitch: 'HonestTrend 的 USDT-M 永续合约版本 — 同样的逻辑，但允许做空。',
			philosophy: '现货只能赌涨，期货能双边接收。同一套 EMA + ADX 信号反过来用就是空头入场。强烈建议低杠杆 (1–3x)，否则资金费会吃掉边际。',
			factors: ['EMA-cross', 'ADX', '允许做空', 'USDT-M 永续', '低杠杆'],
			bestFor: '熊市 / 高波动期 — 多头策略躺平时空头能盈利，覆盖到现货拿不到的市场。',
			worstFor: '振荡盘 + 高资金费 — 双边都被洗 + 持仓成本高，亏得快。',
			risk: '杠杆放大风险。资金费率为正时做多 = 持续付费给对手；务必查看资金费曲线。'
		},
		en: {
			name: 'HonestTrendFutures',
			pitch: 'USDT-M perpetual variant of HonestTrend — same logic but can short.',
			philosophy: 'Spot can only profit on the way up; futures captures both sides. The same EMA + ADX signals fire as longs *or* shorts. Use low leverage (1–3×) — funding rates eat the edge fast.',
			factors: ['EMA-cross', 'ADX', 'short-enabled', 'USDT-M perp', 'low-leverage'],
			bestFor: 'Bear markets / high-vol regimes — captures the down-leg that long-only strategies miss.',
			worstFor: 'Choppy markets with high funding — washed both directions while paying funding.',
			risk: 'Leverage amplifies losses. Positive funding while long = continuous payment to counterparts; always watch the funding curve.'
		}
	},

	LiveProveIt: {
		zh: {
			name: 'LiveProveIt',
			pitch: '内部"概念验证"策略 — 极简逻辑，用来验证某个想法或调试管线。',
			philosophy: '不是给真金白银用的策略。LiveProveIt 是测试基础设施 (数据流 / 信号同步 / 实盘信令) 是否正常的最小可行用例。指标好坏不代表方法好坏。',
			factors: ['infra-test'],
			bestFor: '管线验证 / 调试 — 确认数据流与信令链路端到端可用。',
			worstFor: '任何真实资金场景 — 它不是为盈利设计的。'
		},
		en: {
			name: 'LiveProveIt',
			pitch: 'Internal "proof-of-concept" strategy — minimum viable logic to validate ideas or debug the pipeline.',
			philosophy: 'Not meant for real capital. LiveProveIt exercises the infrastructure (data flow / signal sync / live signaling) end-to-end. Its metrics are about pipeline health, not method quality.',
			factors: ['infra-test'],
			bestFor: 'Pipeline validation / debugging — proving the data flow and signaling chain end-to-end.',
			worstFor: 'Any real-capital scenario — it is not designed to make money.'
		}
	}
};

export function getStrategy(id: string, lang: 'zh' | 'en'): StrategyCopy | null {
	const entry = STRATEGIES[id];
	if (!entry) return null;
	return entry[lang];
}
