// English message bundle. Keep keys in sync with zh.ts; missing keys fall back to zh.
export default {
	// --- language toggle ---
	'lang.toggle': 'Language',
	'lang.zh': '中',
	'lang.en': 'EN',

	// --- topbar ---
	'nav.home': 'Home',
	'nav.start': 'Getting started',
	'nav.nautilus': 'Engine',
	'nav.semis': 'Semis',
	'nav.commodities': 'Commodities',
	'nav.globe': 'Global Markets',
	'nav.strategies': 'Strategies',
	'nav.backtest': 'Backtest',
	'nav.quantLab': 'Quant Lab',
	'nav.dca': 'DCA',
	'nav.chart': 'Chart',
	'nav.archive': 'Archive',
	'nav.wf': 'WF',
	'nav.reports': 'Reports',
	'nav.signals': 'Signals',
	'nav.market': 'Research',
	'nav.aiSemisResearch': 'AI Semis Research',
	'nav.hyperopt': 'Hyperopt',
	'nav.factors': 'Factors',
	'nav.graveyard': 'Graveyard',
	'nav.more': 'Research and tools',
	'nav.docs': 'Docs',
	'nav.record': 'Track record',
	'nav.execution': 'Your accounts',
	'nav.scan': 'Opportunity radar',
	'nav.method': 'Methodology',
	'topbar.login': 'Log in',
	'topbar.logout': 'Log out',
	'topbar.title': 'Quant',

	// --- shared ---
	'common.loading': 'Loading...',
	'common.error': 'Error',
	'common.all': 'All',
	'common.clear': 'Clear filter',
	'common.viewAll': 'View all →',
	'common.enter': 'Enter →',
	'common.detail': 'See details →',
	'common.back': 'Back',
	'common.none': 'None',
	'common.status': 'Status',
	'common.time': 'Time',
	'common.mode': 'Mode',
	'common.pair': 'Pair',
	'common.source': 'Source',
	'common.rows': 'Rows',
	'common.load': 'Load',

	'strategies.title': '📚 Strategy catalog',
	'strategies.subtitle':
		'Every strategy is validated against the full 2017–2026 history and an 8-regime walk-forward. Click through for factor lists, metric distributions, and the matching plotly reports.',
	'strategies.card.runs': 'Runs',
	'strategies.card.tf': 'TF',
	'strategies.card.bestProfit': 'Best profit',
	'strategies.card.bestCalmar': 'Best Calmar',
	'strategies.card.bestSharpe': 'Best Sharpe',
	'strategies.card.worstDd': 'Worst DD',
	'strategies.status.live': 'live',
	'strategies.status.dryrun': 'dryrun',
	'strategies.status.research': 'research',
	'strategies.status.retired': 'retired',
	'strategies.unknown': '(not in static catalog)',

	// --- strategy detail ---
	'detail.breadcrumb': '📚 Strategy catalog',
	'detail.mode': 'Mode',
	'detail.tf': 'Timeframe',
	'detail.pairs': 'Pairs',
	'detail.factors': '🏷️ Factor tags',
	'detail.factorsDesc':
		'Badges are written at backtest ingest (see migrations/003_backtest_factors.sql). Signal (blue), Context (purple), Execution (amber), Risk (red), Mode (green/rose).',
	'detail.mechanics': '📖 How it works',
	'detail.backtestTable': '📊 Backtest metrics (sorted by profit, top {n})',
	'detail.backtestCount': '{n} total',
	'detail.table.imported': 'Imported',
	'detail.table.timerange': 'Timerange',
	'detail.table.trades': 'Trades',
	'detail.table.winRate': 'Win%',
	'detail.table.profit': 'Profit%',
	'detail.table.maxDd': 'MaxDD%',
	'detail.table.calmar': 'Calmar',
	'detail.table.sharpe': 'Sharpe',
	'detail.table.sortino': 'Sortino',
	'detail.table.pf': 'PF',
	'detail.empty': 'No archived backtests yet.',
	'detail.wf': '🧭 Walk-Forward stability',
	'detail.wfRunDate': 'run_date {d}',
	'detail.wfFoot':
		"Each row is a regime window. Red bars mean the strategy lost money in that market — it couldn't survive that regime.",
	'detail.wfLink': 'Full WF matrix →',
	'detail.reports': '📁 Plotly reports',
	'detail.doc': 'Read more:',

	// --- dca ---
	'dca.title': '💰 Smart DCA',
	'dca.subtitle':
		'Smart DCA: one base buy a day, +3 units when Fear & Greed is ≤ 25 (+5 at ≤ 15), and +2 more when BTC is 20%+ below its 30-day high. Buy more in panic and less otherwise to pull the average cost down; boost days are pushed to Telegram.',
	'dca.kpi.scheduled': 'Scheduled buys',
	'dca.kpi.scheduledSub': 'Weekly DCA',
	'dca.kpi.scheduledUsdt': 'Scheduled total',
	'dca.cumEmpty': 'No scheduled DCA records yet (dry_run).',
	'dca.table.fng': 'FnG',
	'dca.table.mode': 'Mode',
	'dca.log.title': '🗓️ Scheduled DCA log (weekly)',
	'dca.log.base': 'Base',
	'dca.log.mult': 'Mult',
	'dca.log.actual': 'Actual',
	'dca.log.cycle': 'Cycle',
	'dca.reports': '📁 DCA plotly reports',
	'dca.report.comparison.title': 'DCA strategy comparison',
	'dca.report.comparison.desc': 'Long-run equity curves across different DCA rules',
	'dca.report.weekly.title': 'DCA backtest — periodic',
	'dca.report.weekly.desc': 'Flat weekly vs. FnG/cycle/news-weighted multiplier',
	'dca.report.dist.title': 'Multiplier distribution',
	'dca.report.dist.desc': 'Per-buy multiplier distribution overlaid on BTC price',

	// --- personal DCA plan (post-login) ---
	'plan.title': '🎯 Your DCA plan (personal simulation)',
	'plan.subtitleAnon':
		'Log in to save your own DCA plan and replay history with the same event signals — see what your stack would look like now.',
	'plan.loginCta': 'Log in →',
	'plan.loading': 'Simulating…',
	'plan.start': 'Start date',
	'plan.monthly': 'Monthly (USDT)',
	'plan.save': 'Save plan',
	'plan.saved': '✓ Saved',
	'plan.preview': 'Preview',
	'plan.emptyResult': 'Configure your plan above and the simulation results appear here.',
	'plan.result.invested': 'Total invested',
	'plan.result.value': 'Current value',
	'plan.result.btc': 'BTC stacked',
	'plan.result.roi': 'ROI',
	'plan.result.scheduled': 'Scheduled buys',
	'plan.result.avgCost': 'Avg cost',
	'plan.digest': '📧 Email me a weekly summary of the bots',
	'plan.digestHint': '(delivery pipeline in progress — your preference is saved now)',
	'plan.greeting': 'Welcome back',
	'plan.greetingPlan': 'Your DCA plan · {invested} → {value} ({roi})',
	'plan.greetingNoPlan': 'No DCA plan yet — set one up in /dca (30 seconds) →',
	'plan.error': 'Error: {msg}',
	'plan.mix': 'Coin mix',
	'plan.mixHint': 'Split BTC / ETH / BNB / SOL by %. Event-triggered buys always go to BTC.',
	'plan.mixError': 'Allocation must sum to 100% (currently {total}%)',
	'plan.normalize': 'Normalize',
	'plan.result.coins': 'Holdings',

	// --- trust + affiliate ---
	'trust.heading': 'Why I built this',
	'trust.body':
		'Crypto accumulation (Smart DCA) and trend (Donchian) now run on NautilusTrader, executing live on the Binance testnet; the US-equity semiconductor leg is in backtest validation. Strategy code, backtests, and live execution are all public — live (testnet) and backtest are clearly separated, no overclaiming.',
	'trust.architecture': 'Architecture',
	'trust.dca': 'DCA plan',
	'affiliate.title': 'No exchange account yet?',
	'affiliate.body':
		'Sign up via my Binance / OKX referral — I get a small commission (free to you, affects nothing), and you can start executing the plan above immediately.',
	'affiliate.disclosure':
		'Disclosure: above are referral links; I receive a commission on your trading fees. This is one of the site’s revenue sources — thanks for the support.',
	'affiliate.inline': 'No exchange account yet? Sign up via my link →',

	// --- chart ---
	'chart.title': 'Multi-granularity chart',
	'chart.subtitle':
		'The server picks ohlc_15m / ohlc_1h / ohlc_1d based on the span — whether you look at 1 day or 8 years, you always get ~2000 points.',
	'chart.range': 'Range',
	'chart.overlay': 'Overlay backtest',
	'chart.legend.enter': 'Entry',
	'chart.legend.winners': '🟢 Winners exit',
	'chart.legend.losers': '🔴 Losers exit',
	'chart.pairTrades': 'Trades on this pair',
	'chart.winRate': 'Win rate',
	'chart.pnl': 'Cumulative P&L',

	// --- archive ---
	'archive.title': 'Backtest archive',
	'archive.subtitle':
		'Filter by strategy / time range / metric to drill into a specific run and its trades.',
	'archive.filter.strategy': 'Strategy',
	'archive.filter.limit': 'Limit',
	'archive.table.id': 'ID',
	'archive.table.started': 'Started',
	'archive.table.strategy': 'Strategy',
	'archive.table.tf': 'TF',
	'archive.table.trades': 'Trades',
	'archive.table.profit': 'Profit%',
	'archive.table.dd': 'MaxDD%',
	'archive.table.calmar': 'Calmar',
	'archive.table.winRate': 'Win%',
	'archive.table.job': 'Job',
	'archive.empty': 'No backtests match those filters.',
	'archive.detailTitle': '#{id} · {strategy} · {timeframe}',
	'archive.close': 'Close ×',
	'archive.table.sortino': 'Sortino',
	'archive.table.pf': 'PF',
	'archive.compare.title': 'Compare Runs',
	'archive.compare.close': 'Close',
	'archive.equity.title': 'Equity Curve',
	'archive.equity.empty': 'No closed trades',

	// --- metric tooltips (shared across archive / home / strategy detail) ---
	'metric.tip.started':
		"Start of the historical window the backtest covers (not the run's wall-clock start).",
	'metric.tip.tf': "Candle timeframe (15m / 1m / 1h…). HTF informative feeds aren't listed here.",
	'metric.tip.trades': 'Number of complete trades (open + close counts as one).',
	'metric.tip.wr':
		'Win rate = wins / total_trades × 100. A low WR with a high PF (typical trend-following) can still beat a high-WR strategy.',
	'metric.tip.profit':
		'Cumulative return (%). (Final equity − starting equity) / starting equity. Trading fees already netted out.',
	'metric.tip.abs': 'Cumulative USD PnL, against the 10K USDT starting equity baseline.',
	'metric.tip.maxDd':
		'Peak-to-trough account drawdown (%). The 20% kill-switch here means anything above 20% is treated as strategy death.',
	'metric.tip.calmar':
		'Calmar = annualised return / MaxDD. > 1 is the bar, > 2 is excellent. Return per unit of drawdown.',
	'metric.tip.sharpe':
		'Sharpe = (annualised return − risk-free) / annualised vol. > 1 bar, > 2 excellent. Punishes up-volatility and down-volatility equally.',
	'metric.tip.sortino':
		'Sortino = (annualised return − risk-free) / downside volatility. Only penalises downside — closer to how traders actually think about risk. > 1.5 is the bar.',
	'metric.tip.pf':
		'Profit factor = gross profit / gross loss. > 1 to make money at all, > 2 is excellent, < 1.2 usually dies in the next drawdown.',
	'metric.tip.pairs':
		'Pairs traded in this run. Futures use BASE/QUOTE:SETTLE (e.g. ETH/USDT:USDT).',
	'metric.tip.factors':
		'Factor tags for this strategy (signal / context / execution / risk / mode). Written at ingest based on strategy name.',

	// --- wf ---
	'wf.title': 'Walk-Forward 8-regime comparison',
	'wf.subtitle':
		'Each strategy runs independently across 8 market-regime windows from 2018-2026 ($10K per window). The LUNA 2022 window (W5) matters most — spot long-only dies there; futures long+short recovers.',

	// --- live ---

	// --- reports ---
	'reports.title': '📁 Backtest reports',
	'reports.subtitle': 'All plotly reports, grouped by backtest.',
	'reports.skipped': '{n} files over 20 MB, pending R2 migration',

	// --- market research ---
	'market.title': 'Market Research',
	'market.subtitle':
		'Weekly quant dashboard combining on-chain data and technical indicators. Data from Binance + Alternative.me (all free public APIs).',
	'market.currentPrice': 'Current Price',
	'market.dataSource': 'Data source',
	'market.signal': 'Signal',
	'market.signal.info': 'Info',
	'market.error': 'Failed to load market data. Please try again later.',
	'market.footer':
		'Sources: Binance REST API · Alternative.me Fear & Greed · Computed on each request',
	'market.section.valuation': 'Valuation',
	'market.section.technicals': 'Technicals',
	'market.section.sentiment': 'Sentiment',
	'market.section.leverage': 'Leverage',
	'market.card.ma4y.title': '4-Year MA Multiple',
	'market.card.ma4y.desc':
		'Current price / 208-week SMA. < 0.8 historically undervalued; > 1.5 historically expensive. Long-term holder anchor.',
	'market.card.ma5w.title': '5-Week MA Direction',
	'market.card.ma5w.desc':
		'Slope direction of the 5-week SMA. Up = short-term bullish momentum; Down = trend weakening.',
	'market.card.macd.title': 'MACD Histogram',
	'market.card.macd.desc':
		'MACD(12,26,9) histogram value. Positive = fast line above slow (bullish momentum); negative = bearish.',
	'market.card.rsi.title': 'RSI(14) Weekly',
	'market.card.rsi.desc':
		'Relative Strength Index on weekly candles. < 35 oversold (potential entry); > 70 overbought (caution).',
	'market.card.stochrsi.title': 'StochRSI K',
	'market.card.stochrsi.desc':
		'Stochastic of RSI on weekly candles. < 20 oversold; > 80 overbought. More sensitive than raw RSI.',
	'market.card.fng.title': 'Fear & Greed Index',
	'market.card.fng.desc':
		'Alternative.me composite index (0–100). Extreme fear (< 25) = historically best buy windows; extreme greed (> 75) = elevated risk.',
	'market.card.funding.title': 'Funding Rate APR',
	'market.card.funding.desc':
		'Annualised perpetual funding rate. > 15% longs overheated; < -5% shorts dominant, potential squeeze rally.',
	'market.card.oi.title': 'Open Interest (USD)',
	'market.card.oi.desc':
		'Total outstanding perpetual futures positions in USD. Sudden sharp drop signals mass liquidation and potential high volatility.',
	'market.derivatives.title': 'Derivatives Sentiment',
	'market.ls.title': 'L/S Account Ratio',
	'market.taker.title': 'Taker Buy/Sell',
	'market.toptrader.title': 'Top Trader L/S',

	// --- signals ---
	'signals.title': '📡 Signal Log',
	'signals.subtitle': 'Strategy signals · DCA event triggers · Backtest runs · All searchable',
	'signals.search': 'Search signals…',
	'signals.empty': 'No signals yet',
	'signals.gate.title': 'Log in to see the full signal log',
	'signals.gate.body': 'Backtest history, DCA event triggers — all on a searchable timeline.',
	'signals.gate.cta': 'Log in →',

	// --- hyperopt ---
	'hyperopt.title': 'Hyperopt Parameter Search',
	'hyperopt.subtitle': 'Loss curve and parameter distribution across epochs',
	'hyperopt.noData.title': 'No Hyperopt data yet',
	'hyperopt.noData.body':
		"Run sops exec-env secrets.env 'python scripts/sync_hyperopt_to_db.py' to sync results.",
	'hyperopt.bestLoss': 'Current best loss',
	'hyperopt.chart.title': 'Loss curve',
	'hyperopt.table.title': 'Top 20 epochs (sorted by loss asc)',
	'hyperopt.col.epoch': 'Epoch',
	'hyperopt.col.loss': 'Loss',
	'hyperopt.col.sharpe': 'Sharpe',
	'hyperopt.col.calmar': 'Calmar',
	'hyperopt.col.sortino': 'Sortino',
	'hyperopt.col.profit': 'Profit',
	'hyperopt.col.winrate': 'Win%',
	'hyperopt.col.trades': 'Trades',
	'hyperopt.col.maxdd': 'MaxDD',
	'hyperopt.col.params': 'Params',
	'hyperopt.scatter.title': 'Params vs Loss scatter',

	// --- login ---
	'login.title': 'Log in',
	'login.email': 'Email',
	'login.password': 'Password',
	'login.submit': 'Log in',
	'login.signup': 'Sign up',
	'login.toggleSignup': 'No account? Sign up',
	'login.toggleLogin': 'Have an account? Log in',
	'login.loading': 'Submitting...',
	'login.google': 'Sign in with Google',
	'login.or': 'or',
	'login.cbTitle': 'Finishing sign-in…',
	'login.cbBody':
		'Got the Google authorisation, storing your session locally. You will be redirected shortly.',
	'login.cbError': 'Sign-in failed: {msg}',
	'login.why':
		'Log in to access {path} — strategy details, backtest archive, and the live feed are for signed-in users only.',
	'login.publicHint': 'Free to browse: home · DCA simulator · docs',

	// --- record (house trend-rule track record, /record) ---
	'record.metaTitle': 'Track record',
	'record.metaDesc':
		'Every trade of our trend-breakout rule across major coins — net of fees, with win rate and a buy-and-hold comparison, losses included. Rule-based simulated signals, not investment advice.',
	'record.metaDescLive':
		'Since {start}, $1,000 following every signal → {follow} vs {hold} buying and holding; {n} closed trades, {win} win rate, net of fees, losses included. Rule-based simulated signals, not investment advice.',
	'record.share': 'Share',
	'record.shareCopied': 'Link copied',
	'record.eyebrow': 'Rule-based simulated signals · public record',
	'record.title': 'Track record',
	'record.subtitle':
		'One trend-breakout rule, applied to {assets}: buy when an hourly candle closes above the highest price of the past 7 days, sell when one closes below the lowest price of the past 3 days. Below is every trade since {start}, winners and losers alike, with fees already deducted.',
	'record.headline': 'If you had put $1,000 in on {start}, split equally across {assets}',
	'record.kpi.follow': 'Following every signal',
	'record.kpi.followSub': '{ret} after fees',
	'record.kpi.hold': 'Buy and hold instead',
	'record.kpi.holdSub': '{ret}, just holding',
	'record.kpi.trades': 'Closed trades',
	'record.kpi.tradesSub': 'plus {n} open now',
	'record.kpi.tradesSubNone': 'no open position',
	'record.kpi.winRate': 'Win rate',
	'record.kpi.winRateSub': '{w} of {n} made money',
	'record.kpi.best': 'Best trade',
	'record.kpi.bestSub': '{asset}, after fees',
	'record.asOf': 'Data as of {ts} UTC, updated after every hourly close.',
	'record.split': '{b} trades are backfilled, {l} recorded live.',
	'record.assets.title': 'Where each coin stands now',
	'record.assets.count': '{n} coins',
	'record.assets.sub': 'Binance spot hourly closes, refreshed after every hourly close.',
	'record.state.long': 'Holding',
	'record.state.flat': 'Waiting',
	'record.card.bought': 'Bought at',
	'record.card.boughtAt': 'bought {ts} UTC',
	'record.card.last': 'Last close',
	'record.card.openRet': 'Open P/L (after fees)',
	'record.card.exitLine': 'Exit line',
	'record.card.exitHint': 'Sells if an hourly candle closes below the exit line.',
	'record.card.trigger': 'Buy trigger',
	'record.card.triggerHint': 'Buys if an hourly candle closes above the trigger.',
	'record.card.fromLast': '{pct} from last close',
	'record.card.since': 'Since {start}',
	'record.card.strategy': 'Strategy',
	'record.card.hold': 'buy and hold',
	'record.card.stats': '{n} closed · {w} made money',
	'record.card.avg': 'Avg win {win} · avg loss {loss}',
	'record.src.live': 'Live',
	'record.src.backfill': 'Backfilled',
	'record.src.liveHint': 'Recorded in real time as the signal fired',
	'record.src.backfillHint':
		'Computed afterwards by replaying the same rule on past prices — not a call made at the time',
	'record.cta.title': 'Get the next signal the moment it fires',
	'record.cta.sub':
		'Bind Telegram and tick "Strategy buy/sell signals": you get every buy, every exit and a weekly scorecard, each with its exit rule.',
	'record.trades.title': 'Every trade',
	'record.trades.sub': '{n} trades, newest first. Times in UTC, returns after fees.',
	'record.col.asset': 'Coin',
	'record.col.entry': 'Bought',
	'record.col.exit': 'Sold',
	'record.col.ret': 'Return',
	'record.col.days': 'Held',
	'record.col.source': 'Source',
	'record.trades.holding': 'Holding',
	'record.trades.floating': 'open',
	'record.trades.days': '{n} d',
	'record.trades.showAll': 'Show all {n} trades',
	'record.trades.showLess': 'Show fewer',
	'record.trades.empty': 'No trades yet.',
	'record.rules.title': 'How the rule works',
	'record.rules.buy':
		'Buy: an hourly candle closes above the highest price of the past 7 days (168 hourly candles).',
	'record.rules.sell':
		'Sell: while holding, an hourly candle closes below the lowest price of the past 3 days (72 hourly candles).',
	'record.rules.scope':
		'Long only, no leverage. Each coin runs on its own and is either fully in or fully out.',
	'record.rules.portfolio':
		'Portfolio: the money is split equally across the coins, each following its own signals, never rebalanced. The buy-and-hold comparison is split the same way and starts at the same moment.',
	'record.rules.universe':
		"How the coins were chosen: on 2026-09-27 they were screened from Binance's top 30 USDT pairs by trading volume, using only 2024–2025 data and criteria fixed in advance — two full years of data, a positive return after fees, a maximum drawdown shallower than buy and hold, and return / max drawdown of at least 0.5. So the 2026 record shown here is out-of-sample for that selection; it is still a backfilled replay, not calls made at the time, and is labelled as such below.",
	'record.rules.fees':
		'Fees: 0.1% is deducted on every buy and every sell (Binance spot taker rate). Open trades are valued as if sold at the latest hourly close, fees included.',
	'record.honest.title': 'Honestly',
	'record.honest.body':
		'Most trend signals end in a small loss; the money comes from a few big trends. Follow only a handful and you may well miss the one that pays. In sideways markets the rule racks up small losses in a row, and it can trail buy and hold.',
	'record.honest.stats':
		'Since {start}, {w} of {n} closed trades made money (win rate {rate}); the best was {asset} {best}.',
	'record.backfill.title': 'What "Backfilled" means',
	'record.backfill.body':
		'Trades marked "Backfilled" were computed afterwards by replaying the same rule on past prices. They are not calls made at the time.',
	'record.backfill.since':
		'From {since}, new signals are marked "Live": recorded right after the hourly close and pushed to subscribers.',
	'record.disclaimer':
		'Rule-based simulated signals, not investment advice. We do not manage money or give position-sizing advice. Past performance does not guarantee future results.',
	'record.empty.title': 'The track record is being prepared',
	'record.empty.body':
		'The historical backfill has not run yet. Every trade will be listed here once it has.',
	'record.error.title': 'The track record could not be loaded',
	'record.error.body':
		'The data service is unreachable right now. Please refresh in a little while.',
	'record.live.title': 'Live signals since launch',
	'record.live.sub':
		'Only signals pushed to subscribers in real time after launch — no backfilled trades.',
	'record.live.signals': 'Buy signals pushed',
	'record.live.signalsSub': '{c} closed · {o} still held',
	'record.live.winRateSub': '{w} of {n} live closed trades made money',
	'record.live.ret': 'Closed trades, compounded',
	'record.live.retSub': 'net of fees',
	'record.live.small':
		'Small sample: only {n} live trades have closed (fewer than {min}), so the win rate and return will swing a lot. Most of the full record above is backfilled.',
	'record.live.none':
		'No new buy signal since launch yet. Breakouts need the market to move; it can take days.',
	'record.live.first': 'First live signal: {ts} UTC.',
	'record.live.method':
		'Compounded = every trade followed in turn with the same money — not the equal split across coins used above.',
	'record.mine.title': 'My follows',
	'record.mine.sub': 'Signals you marked as "I followed this". Only you can see this section.',
	'record.mine.empty':
		'Nothing marked yet. Tap "I followed this" under a Telegram buy signal, or "I followed" in the trade list below. Only signals that were pushed live can be marked.',
	'record.mine.followed': 'Marked',
	'record.mine.followedSub': '{c} closed · {o} still held',
	'record.mine.ret': 'Closed trades, compounded',
	'record.mine.retSub': 'at signal prices, net of fees',
	'record.mine.winRateSub': '{w} of {n} made money',
	'record.mine.note':
		'Computed at the signal price with 0.1% fees per side — not your real fills; every trade compounded in turn with the same money. Your actual prices, size and timing differ, and so will your result.',
	'record.mine.tg':
		'Send /me to the Telegram bot for a shareable card of this record (no name on it).',
	'record.mine.error': 'Could not load your follows. Please refresh in a little while.',
	'record.mine.loading': 'Loading…',
	'record.follow.col': 'Follow',
	'record.follow.mark': 'I followed',
	'record.follow.marked': 'Followed ✓',
	'record.follow.unmark': 'Unmark',
	'record.follow.markHint': 'Mark that you followed this signal; it counts toward "My follows"',
	'record.follow.backfillHint': 'Backfilled trades were never pushed, so they cannot be marked',
	'record.methodLink': 'Rules, costs, data sources and rejected ideas — see the methodology →',

	// --- nautilus (execution engine) ---
	'nautilus.superseded': 'Superseded',
	'nautilus.supersededHint':
		'An engine restart re-registered this position as a new row; this row is a stale copy with no real exit price or P&L.',
	'nautilus.recordLink': 'Looking for every buy and sell of the trend rule?',
	'nautilus.recordCta': 'Track record →',

	// --- scan (opportunity radar, /scan) ---
	'scan.metaTitle': 'Opportunity radar',
	'scan.metaDesc':
		'Opportunity radar for crypto, US stocks and commodities: which coins are near a trend-rule buy or exit, where perp funding is crowded, and how far each stock and commodity is from its 52-week high and 200-day average, with the VIX. Rule-based observations, not investment advice.',
	'scan.eyebrow': 'Rule-based observations · crypto hourly, stocks and commodities daily',
	'scan.title': 'Opportunity radar',
	'scan.subtitle':
		'The same trend rule as the track record, run across all {n} coins: which are a small move away from their buy trigger, which holdings are close to their exit line, and which have fallen furthest from their 30-day high. Plus perpetual funding rates, to see which side is most crowded.',
	'scan.asOf': 'Prices as of {ts} UTC (Binance spot 1-hour close).',
	'scan.fundingAsOf': 'Funding updated {ts} UTC.',
	'scan.kpi.nearEntry': 'Near a buy trigger',
	'scan.kpi.nearEntrySub': 'Flat and within {near} of the trigger',
	'scan.kpi.nearExit': 'Near the exit line',
	'scan.kpi.nearExitSub': 'Held and within {near} of the exit line',
	'scan.kpi.dip': 'Deep dip',
	'scan.kpi.dipSub': '{dip} or more below the 30-day high',
	'scan.kpi.funding': 'Extreme funding',
	'scan.kpi.fundingSub': 'Annualised ≥ {hot} or ≤ {cold}',
	'scan.entry.title': 'Near a buy trigger',
	'scan.entry.sub':
		'Coins the rule is waiting on, closest to the trigger first. A 1-hour close above the trigger is a buy; those within {near} are highlighted.',
	'scan.exit.title': 'Near the exit line',
	'scan.exit.sub':
		'Coins the rule holds, closest to the exit line first. A 1-hour close below the exit line is a sell; those within {near} are highlighted.',
	'scan.dip.title': 'Deep dips',
	'scan.dip.sub':
		'Every coin by its drop from the 30-day high; {dip} or more is highlighted. This is only an observation: a big drop is not a buy signal, and the trend rule still waits for a breakout.',
	'scan.dip.noData': '"—" means the coin has less than 30 days of 1-hour closes so far.',
	'scan.col.asset': 'Coin',
	'scan.col.last': 'Last close',
	'scan.col.trigger': 'Buy trigger',
	'scan.col.toEntry': 'To trigger',
	'scan.col.exitLine': 'Exit line',
	'scan.col.toExit': 'To exit',
	'scan.col.high30d': '30-day high',
	'scan.col.fromHigh': 'From high',
	'scan.heldSince': 'held since {ts}',
	'scan.flag.near': 'within {near}',
	'scan.flag.dip': 'deep dip',
	'scan.none.entry': 'No coin is flat right now: the rule holds all of them.',
	'scan.none.exit': 'Nothing is held right now: the rule is waiting on every coin.',
	'scan.recordLink': 'Every buy and sell per coin, with net returns, is in the',
	'scan.recordCta': 'track record →',
	'scan.funding.title': 'Funding radar',
	'scan.funding.sub':
		'The {n} coins with both a Binance USDT perpetual and a spot market, by their last 7 days of actual funding, annualised, highest first. ≥ {hot} a year is flagged as crowded longs, ≤ {cold} as crowded shorts.',
	'scan.funding.col.asset': 'Coin',
	'scan.funding.col.ann': '7-day annualised',
	'scan.funding.col.last': 'Last rate',
	'scan.funding.col.vol': '24h volume',
	'scan.funding.hot': 'crowded longs',
	'scan.funding.cold': 'crowded shorts',
	'scan.funding.empty': 'No funding data yet.',
	'scan.carry.title': 'What funding is, and whether you can earn it',
	'scan.carry.what':
		'Perpetual futures never expire, so every few hours longs and shorts pay each other a funding fee that keeps the contract near spot. Positive funding means longs pay shorts: more people want to be long, longs are crowded. Negative funding means shorts pay longs: shorts are crowded.',
	'scan.carry.how':
		'The usual trade is the "carry": buy the coin spot and short the same amount on the perpetual. Price moves cancel out and you collect the funding.',
	'scan.carry.backtest':
		'Our backtest (Jan 2024 – Sep 2026, four fees per round trip, annualised on the position): running the BTC carry all the time made +11.7% in 2024, +5.1% in 2025 and only +2.7% so far in 2026 — halve that for the return on capital, since spot and margin each tie up half. Rotating weekly into the 3 coins with the highest funding lost 3.9% in 2026: high funding tends to fade fast and switching fees eat the rest. So read this table mainly as a sentiment gauge: the more crowded the longs, the more careful you should be chasing a move.',
	'scan.risk.title': 'It is not risk-free income',
	'scan.risk.fees':
		'Opening and closing both legs costs four trading fees; low funding or a short hold gets eaten by fees.',
	'scan.risk.flip':
		'Funding changes all the time and can turn negative, and then you pay the longs. The table shows the last 7 days annualised, not a promised yield.',
	'scan.risk.liq':
		'If the short leg is under-margined, a sharp rally liquidates it while the spot leg stays, and the hedge is gone.',
	'scan.risk.exchange':
		'Funds on an exchange carry the exchange risk itself: withdrawal halts, insolvency or hacks.',
	'scan.cta.title': 'Get the radar every morning',
	'scan.cta.sub':
		'Bind Telegram and tick "Daily opportunity radar": every day at 08:30 Beijing time you get the coins near a trigger, the deep dips, the extreme funding and the stock and commodity highs and drawdowns.',
	'scan.disclaimer':
		'Rule-based observations, not investment advice. We do not manage money or give position sizing advice.',
	'scan.methodLink':
		'Radar thresholds, and why funding is only a sentiment gauge — see the methodology →',
	'scan.empty.title': 'The radar is warming up',
	'scan.empty.body': 'No price data yet; it updates after every hourly close.',
	'scan.error.title': 'The radar could not load',
	'scan.error.body': 'The data service is unreachable right now. Please refresh in a moment.',
	'scan.lead':
		'One tab per asset class. Crypto: how far each coin is from its trend-rule buy or exit level, plus perp funding. US stocks and commodities: how far each price is from its 52-week high and whether it is above its 200-day average. Rule-based observations, not investment advice.',
	'scan.tab.crypto': 'Crypto',
	'scan.tab.equity': 'US stocks',
	'scan.tab.commodity': 'Commodities',
	'scan.mkt.equity.sub':
		'The S&P 500, Nasdaq 100, Russell 2000 and semiconductor ETFs, 8 tech mega caps and the NVIDIA supply chain, closest to their 52-week closing high first.',
	'scan.mkt.commodity.sub':
		'Twelve continuous futures (gold, silver, crude, copper, natural gas, grains and more), closest to their 52-week closing high first.',
	'scan.mkt.asOf': 'Daily closes as of {d} (US session); updated every day after the US close.',
	'scan.mkt.empty.title': 'No data for this market yet',
	'scan.mkt.empty.body': 'Daily closes update after every US close; please check back later.',
	'scan.mkt.kpi.vix': 'VIX',
	'scan.mkt.kpi.vixSub': 'Above 20 is tense, above 30 is fear',
	'scan.mkt.kpi.nearHigh': 'Near the 52-week high',
	'scan.mkt.kpi.nearHighSub': 'Within {near} of the 52-week closing high',
	'scan.mkt.kpi.deep': 'Deep drawdown',
	'scan.mkt.kpi.deepSub': '{deep} or more below the 52-week closing high',
	'scan.mkt.kpi.aboveMa': 'Above the 200-day average',
	'scan.mkt.kpi.aboveMaSub': 'Close above its 200-day average price',
	'scan.mkt.table.title': 'Distance from the 52-week high',
	'scan.mkt.table.sub':
		'Within {near} of the 52-week closing high is flagged as near the high; {deep} or more below it as a deep drawdown. "vs 200-day" is how far the close is above (+) or below (−) its 200-day average.',
	'scan.mkt.col.equity': 'Stock',
	'scan.mkt.col.commodity': 'Commodity',
	'scan.mkt.col.high52w': '52-week high',
	'scan.mkt.col.fromHigh': 'From high',
	'scan.mkt.col.vsMa': 'vs 200-day',
	'scan.mkt.col.ret1m': '1 month',
	'scan.mkt.flag.near': 'within {near}',
	'scan.mkt.flag.deep': 'down {deep}+',
	'scan.mkt.grp.index': 'Index ETF',
	'scan.mkt.grp.mega': 'Mega cap',
	'scan.mkt.grp.semis': 'NVIDIA supply chain',
	'scan.mkt.grp.metals': 'Metals',
	'scan.mkt.grp.energy': 'Energy',
	'scan.mkt.grp.ags': 'Agriculture',
	'scan.mkt.grp.other': 'Other',
	'scan.mkt.unitNote':
		'Prices are continuous-futures quotes in the unit of each contract (grains in US cents per bushel); they are only used for distances and changes.',
	'scan.mkt.why.title': 'Why there is no buy trigger here',
	'scan.mkt.why.equity':
		'We backtested a daily breakout rule on these stocks (buy on a 100-day closing high, sell below the 50-day low), picking its settings on 2014–2023 only and then checking 2024 to now. Net of fees the rule made +106.6% with a −25.8% drawdown; simply holding made +261.1% with −36.3%. The drawdown was smaller, but it gave up far more return than it saved: only 10 of 46 stocks beat holding on return per unit of drawdown. So this tab shows observations, not buy or sell points.',
	'scan.mkt.why.commodity':
		'We backtested a daily breakout rule on these 12 futures (buy on a 252-day closing high, sell below the 10-day low), picking its settings on 2017–2023 only and then checking 2024 to now. Net of fees the rule made +0.9%; simply holding made +51.8%, and not one of the 12 beat holding. So this tab shows observations, not buy or sell points.',
	'scan.mkt.why.use':
		'How to read it: near the 52-week high means a strong trend, but plan your exit before chasing it; a deep drawdown only means it fell a lot, not that it is cheap, let alone a buy.',

	'web.research_signals_trade_on_your_terms_starslab':
		'Research signals. Trade on your terms. · Starslab',
	'web.explore_transparent_strategy_research_review_recorded_signals_and_connect_an_owner_operate':
		'Explore transparent strategy research, review recorded signals and connect an owner-operated HTX runner. Your keys and trading stay on your device.',
	'web.public_research_visible_assumptions_and_private_account_reports_execution_stays_on_your_co':
		'Public research, visible assumptions and private account reports. Execution stays on your computer or server.',
	'web.open_research_owner_operated_execution': 'Open research · Owner-operated execution',
	'web.understand_the_rules': 'Understand the rules.',
	'web.trade_on_your_terms': 'Trade on your terms.',
	'web.explore_the_evidence_behind_a_strategy_test_your_own_ideas_and_review_your_account_in_one_':
		'Explore the evidence behind a strategy, test your own ideas and review your account in one place. Live execution and exchange keys stay on your computer or server.',
	'web.review_the_track_record': 'Review the track record',
	'web.connect_your_runner': 'Connect your runner',
	'web.new_here_start_with_the_three_minute_guide': 'New here? Start with the three-minute guide',
	'web.choose_your_next_step': 'Choose your next step',
	'web.understand_the_strategy': 'Understand the strategy',
	'web.review_the_house_rules_recorded_signals_losses_and_historical_comparisons':
		'Review the house rules, recorded signals, losses and historical comparisons.',
	'web.explore_the_track_record': 'Explore the track record',
	'web.test_your_own_ideas': 'Test your own ideas',
	'web.explore_historical_backtests_and_inspect_assumptions_before_drawing_conclusions':
		'Explore historical backtests and inspect assumptions before drawing conclusions.',
	'web.open_the_research_playground': 'Open the research playground',
	'web.connect_your_own_account': 'Connect your own account',
	'web.run_the_open_source_htx_executor_on_your_device_and_keep_a_private_view_of_its_reports':
		'Run the open-source HTX executor on your device and keep a private view of its reports.',
	'web.set_up_your_account_display': 'Set up your account display',
	'web.public_research_hourly_donchian_rule': 'Public research · Hourly Donchian rule',
	'web.the_current_house_rule_snapshot': 'The current house-rule snapshot',
	'web.refreshing': 'Refreshing…',
	'web.refresh_data': 'Refresh data',
	'web.data_unavailable': 'Data unavailable',
	'web.update_delayed': 'Update delayed',
	'web.hourly_data': 'Hourly data',
	'web.could_not_refresh_the_previous_snapshot_remains_visible_check_its_timestamp_before_using_i':
		'Could not refresh. The previous snapshot remains visible; check its timestamp before using it.',
	'web.oldest_asset_close': 'Oldest asset close:',
	'web.utc_historical_baseline': 'UTC. Historical baseline:',
	'web.some_prices_are_over_three_hours_old_the_figures_below_are_historical_not_a_current_tradin':
		'Some prices are over three hours old. The figures below are historical, not a current trading instruction.',
	'web.research_assets': 'Research assets',
	'web.open_rule_signals': 'Open rule signals',
	'web.closed_rule_trades': 'Closed rule trades',
	'web.model_return': 'Model return',
	'web.equal_weight_buy_and_hold_comparison': 'Equal-weight buy-and-hold comparison:',
	'web.over_the_same_history': 'over the same history.',
	'web.the_model_includes_reconstructed_history_and_assumes_0_1_fees_per_side_these_are_rule_base':
		'The model includes reconstructed history and assumes 0.1% fees per side. These are rule-based research returns, not real-account returns. Your exchange fees and execution prices may differ.',
	'web.the_research_snapshot_could_not_be_loaded_missing_data_is_not_shown_as_zero_returns_or_no_':
		'The research snapshot could not be loaded. Missing data is not shown as zero returns or no signals. You can still explore the methodology and set up your private account display.',
	'web.full_history_and_live_recording_split': 'Full history and live-recording split →',
	'web.rules_assumptions_and_costs': 'Rules, assumptions and costs →',
	'web.observe_the_market': 'Observe the market',
	'web.delayed_reading': ' · delayed reading',
	'web.the_market_stress_reading_is_currently_unavailable':
		'The market stress reading is currently unavailable.',
	'web.these_observations_provide_context_they_do_not_place_trades':
		'These observations provide context; they do not place trades.',
	'web.updated': 'Updated',
	'web.market_context': 'Market context →',
	'web.opportunity_radar': 'Opportunity radar →',
	'web.semiconductor_research': 'Semiconductor research →',
	'web.a_private_view_not_a_managed_account': 'A private view, not a managed account',
	'web.connect_an_upload_only_display_token_to_review_positions_actual_fees_and_recent_fills_star':
		'Connect an upload-only display token to review positions, actual fees and recent fills. Start, stop and fund the executor on your own device.',
	'web.read_the_open_source_setup_guide': 'Read the open-source setup guide',
	'web.historical_research_can_lose_money_and_does_not_predict_future_returns_public_testnet_and_':
		'Historical research can lose money and does not predict future returns. Public testnet and paper fills are demonstrations; private runner reports come from each account owner.',
	'web.getting_started_starslab': 'Getting started · Starslab',
	'web.understand_starslab_research_test_strategies_and_connect_a_private_owner_operated_htx_runn':
		'Understand Starslab research, test strategies and connect a private owner-operated HTX runner. Learn where keys stay, how budgets work and how to stop trading.',
	'web.research_first_execute_on_your_device_keep_your_account_reports_private':
		'Research first. Execute on your device. Keep your account reports private.',
	'web.getting_started': 'Getting started',
	'web.a_clear_path_from_research_to_your_own_account':
		'A clear path from research to your own account',
	'web.starslab_publishes_research_and_displays_account_reports_you_decide_what_to_run_the_live_e':
		'Starslab publishes research and displays account reports. You decide what to run. The live executor runs on your computer or server and keeps exchange credentials and order recovery on that device.',
	'web.read_the_evidence': 'Read the evidence',
	'web.start_with_the_public_house_rule_record_compare_the_strategy_with_buy_and_hold_check_the_h':
		'Start with the public house-rule record. Compare the strategy with buy-and-hold, check the historical versus live-recorded split and read the cost assumptions.',
	'web.explore_before_committing': 'Explore before committing',
	'web.use_the_backtest_playground_to_inspect_a_strategy_testnet_and_paper_fills_demonstrate_exec':
		'Use the backtest playground to inspect a strategy. Testnet and paper fills demonstrate execution; they are separate from the public research record and your real account.',
	'web.try_the_research_playground': 'Try the research playground',
	'web.run_on_your_own_device': 'Run on your own device',
	'web.if_you_choose_live_execution_install_the_open_source_htx_runner_on_your_computer_or_server':
		'If you choose live execution, install the open-source HTX runner on your computer or server. Trading permissions, budgets, keys and the durable journal stay there.',
	'web.connect_a_private_account_display': 'Connect a private account display',
	'web.your_first_runner_connection': 'Your first runner connection',
	'web.step': 'Step',
	'web.install_the_open_source_runner_using_the_official_setup_guide_a_fresh_installation_starts_':
		'Install the open-source runner using the official setup guide. A fresh installation starts in simulation.',
	'web.run_a_simulation_and_inspect_its_local_status_review_the_strategy_budget_limits_and_order_':
		'Run a simulation and inspect its local status. Review the strategy, budget limits and order recovery behavior.',
	'web.sign_in_to_your_accounts_choose_the_report_type_matching_your_local_runner_and_download_th':
		'Sign in to Your accounts, choose the report type matching your local runner and download the reporting configuration.',
	'web.attach_the_reporting_file_on_your_device_verify_that_the_account_display_receives_a_recent':
		'Attach the reporting file on your device. Verify that the account display receives a recent report.',
	'web.if_you_choose_live_trading_configure_and_authorize_it_locally_confirm_deposited_funding_an':
		'If you choose live trading, configure and authorize it locally, confirm deposited funding and start your own service. Create a live display connection to match it.',
	'web.open_your_accounts': 'Open Your accounts',
	'web.install_and_operate_the_runner': 'Install and operate the runner',
	'web.questions_before_you_connect': 'Questions before you connect',
	'web.want_to_understand_the_rule_before_using_it': 'Want to understand the rule before using it?',
	'web.read_the_methodology_and_cost_assumptions': 'Read the methodology and cost assumptions →',
	'web.is_the_public_track_record_my_actual_return': 'Is the public track record my actual return?',
	'web.no_it_models_the_published_rule_includes_reconstructed_history_and_assumes_0_1_fees_per_si':
		'No. It models the published rule, includes reconstructed history and assumes 0.1% fees per side. Your exchange fees, fills and position sizes may differ. Your accounts shows the data your own runner reports.',
	'web.does_connecting_a_display_start_trading': 'Does connecting a display start trading?',
	'web.no_the_downloaded_configuration_contains_an_upload_only_token_it_lets_your_local_runner_se':
		'No. The downloaded configuration contains an upload-only token. It lets your local runner send positions, fees and recent fills. Live trading requires explicit authorization on your own device.',
	'web.where_do_i_put_my_exchange_keys': 'Where do I put my exchange keys?',
	'web.only_on_the_computer_or_server_running_your_executor_use_a_dedicated_spot_account_with_rea':
		'Only on the computer or server running your executor. Use a dedicated spot account with read and trade permissions. Do not enable withdrawals or paste exchange keys into the website, Telegram or chat.',
	'web.how_do_monthly_budgets_work': 'How do monthly budgets work?',
	'web.choose_limits_locally_and_confirm_deposited_funding_with_the_runner_a_new_calendar_month_d':
		'Choose limits locally and confirm deposited funding with the runner. A new calendar month does not invent a deposit. Trend sale proceeds can be reused; current-month DCA funding remains separate. The setup guide explains how to stop the runner, confirm funding and restart it.',
	'web.how_do_i_stop_trading': 'How do I stop trading?',
	'web.stop_the_executor_on_your_own_computer_or_server_disconnecting_the_display_only_stops_repo':
		'Stop the executor on your own computer or server. Disconnecting the display only stops reporting and does not stop local trading.',
	'web.what_does_an_old_or_missing_report_mean': 'What does an old or missing report mean?',
	'web.it_means_the_website_has_no_recent_update_the_local_executor_may_still_be_running_check_th':
		'It means the website has no recent update. The local executor may still be running. Check the service on your own device; the platform does not send stop or start commands.',
	'web.which_exchanges_are_supported': 'Which exchanges are supported?',
	'web.the_public_runner_currently_supports_htx_spot_live_execution_and_simulation_gate_live_exec':
		'The public runner currently supports HTX spot live execution and simulation. Gate live execution is not included. The public demo execution pages use testnet or paper accounts.',
	'web.are_fees_and_risk_hidden': 'Are fees and risk hidden?',
	'web.private_runner_reports_use_reconciled_fill_fees_including_base_asset_deductions_account_va':
		'Private runner reports use reconciled fill fees, including base-asset deductions. Account value is estimated using hourly research closes and excludes future sell fees. Historical results do not predict future returns.',
	'web.your_accounts_starslab': 'Your accounts · Starslab',
	'web.private_displays_for_trading_runners_on_your_own_computer_or_server_your_exchange_keys_sta':
		'Private displays for trading runners on your own computer or server. Your exchange keys stay with you.',
	'web.your_machine_your_keys': 'Your machine. Your keys.',
	'web.your_accounts': 'Your accounts',
	'web.run_the_open_source_executor_on_your_computer_or_server_starslab_displays_the_account_data':
		'Run the open-source executor on your computer or server. Starslab displays the account data your runner uploads. Trading and exchange credentials stay on your machine.',
	'web.refresh_account_displays': 'Refresh account displays',
	'web.how_connection_works': 'How connection works',
	'web.install_your_runner': 'Install your runner',
	'web.use_a_dedicated_spot_account_configure_exchange_permissions_and_trading_limits_locally':
		'Use a dedicated spot account. Configure exchange permissions and trading limits locally.',
	'web.connect_the_display': 'Connect the display',
	'web.download_a_reporting_configuration_here_it_contains_an_upload_token_never_an_exchange_key':
		'Download a reporting configuration here. It contains an upload token, never an exchange key.',
	'web.review_your_account': 'Review your account',
	'web.see_positions_actual_fees_and_recent_fills_start_and_stop_trading_on_your_own_machine':
		'See positions, actual fees and recent fills. Start and stop trading on your own machine.',
	'web.open_source_runner_and_setup_guide': 'Open-source runner and setup guide ↗',
	'web.loading_your_account_displays': 'Loading your account displays…',
	'web.a_private_view_of_your_account': 'A private view of your account',
	'web.sign_in_to_create_a_display_connection_account_reports_are_visible_only_to_you':
		'Sign in to create a display connection. Account reports are visible only to you.',
	'web.sign_in': 'Sign in',
	'web.connect_your_htx_runner': 'Connect your HTX runner',
	'web.choose_the_report_type_to_match_your_local_runner_this_does_not_enable_trading':
		'Choose the report type to match your local runner. This does not enable trading.',
	'web.save_your_reporting_configuration': 'Save your reporting configuration',
	'web.the_upload_token_is_shown_once_keep_the_file_on_your_runner_s_machine_it_permits_uploads_t':
		"The upload token is shown once. Keep the file on your runner's machine. It permits uploads to this display only.",
	'web.save_display_json': 'Save display.json',
	'web.i_saved_the_file': 'I saved the file',
	'web.account_label': 'Account label',
	'web.report_type': 'Report type',
	'web.simulation': 'Simulation',
	'web.live_spot_account': 'Live spot account',
	'web.creating': 'Creating…',
	'web.create_display_connection': 'Create display connection',
	'web.no_accounts_connected_yet_your_first_report_will_appear_here_after_your_local_runner_start':
		'No accounts connected yet. Your first report will appear here after your local runner starts uploading.',
	'web.live_spot': 'Live spot',
	'web.user_reported_data': '· User-reported data',
	'web.waiting_for_first_report': 'Waiting for first report',
	'web.report_is_stale': 'Report is stale',
	'web.reporting': 'Reporting',
	'web.observed': 'Observed',
	'web.valuation_uses_hourly_research_closes_these_figures_are_supplied_by_your_runner_and_are_no':
		'. Valuation uses hourly research closes. These figures are supplied by your runner and are not independently verified by Starslab.',
	'web.tracked_equity': 'Tracked equity',
	'web.tracked_cash': 'Tracked cash',
	'web.net_contributions': 'Net contributions',
	'web.actual_fees': 'Actual fees',
	'web.simulated_fees': 'Simulated fees',
	'web.estimated_net_p_l': 'Estimated net P&L',
	'web.available_trend_budget': '· Available trend budget',
	'web.current_month_dca': '· Current-month DCA',
	'web.positions': 'Positions',
	'web.no_open_positions': 'No open positions.',
	'web.asset': 'Asset',
	'web.strategy': 'Strategy',
	'web.quantity': 'Quantity',
	'web.value': 'Value',
	'web.realized_p_l': 'Realized P&L',
	'web.btc_dca': 'BTC DCA',
	'web.trend': 'Trend',
	'web.recent_fills': 'Recent fills',
	'web.no_fills_reported_yet': 'No fills reported yet.',
	'web.time': 'Time',
	'web.trade': 'Trade',
	'web.quote_value': 'Quote value',
	'web.fee': 'Fee',
	'web.buy': 'Buy',
	'web.sell': 'Sell',
	'web.disconnect_reporting': 'Disconnect reporting',
	'web.disconnecting_stops_uploads_only_stop_trading_on_the_computer_or_server_running_your_execu':
		'Disconnecting stops uploads only. Stop trading on the computer or server running your executor.',
	'web.account_displays_are_temporarily_unavailable':
		'Account displays are temporarily unavailable.',
	'web.could_not_create_the_display_connection': 'Could not create the display connection.',
	'web.could_not_disconnect_reporting': 'Could not disconnect reporting.',
	'web.sign_in_to_connect_your_local_runner_and_view_your_private_account_reports':
		'Sign in to connect your local runner and view your private account reports.',
	'web.your_account_reports_are_visible_only_to_you':
		'Your account reports are visible only to you.',
	'web.trading_and_exchange_credentials_stay_on_your_machine':
		'Trading and exchange credentials stay on your machine.',
	'web.no_exchange_credentials_are_required_here': 'No exchange credentials are required here.'
};
