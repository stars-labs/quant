import type { PageServerLoad } from './$types';
import { vps, supabase } from '$lib/api';
import type { BacktestRun, OhlcRow, PublicStats } from '$lib/types';

// Home is the funnel's top surface: anon gets public-preview aggregates,
// authed gets the same PLUS richer Recent-25 table and full OHLC.

export const load: PageServerLoad = async ({ fetch, cookies }) => {
	const jwt = cookies.get('qt_jwt');
	const auth = jwt ? `Bearer ${jwt}` : undefined;
	const isAuthed = Boolean(jwt);

	const ohlcFor = (pair: string) =>
		isAuthed
			? vps
					.ohlcDaily(fetch, pair, { from: '2017-01-01', limit: 4000, authHeader: auth })
					.catch(() => [] as OhlcRow[])
			: pair === 'BTC/USDT' || pair === 'ETH/USDT' || pair === 'BNB/USDT' || pair === 'SOL/USDT'
				? vps
						.publicOhlcDaily(fetch, pair, { from: '2017-01-01', limit: 4000 })
						.catch(() => [] as OhlcRow[])
				: Promise.resolve([] as OhlcRow[]);

	const [
		statsRow,
		nautilusBT,
		equityTrades,
		semiUniverse,
		semiGroups,
		runs,
		dca,
		kol,
		btcOhlc,
		ethOhlc,
		bnbOhlc,
		solOhlc
	] = await Promise.all([
		// Honest current numbers: aggregates over the deployed strategies re-run on Nautilus,
		// NOT the retired freqtrade backtest_runs.
		vps.nautilusStats(fetch).catch(() => [] as PublicStats[]),
		vps.nautilusBacktests(fetch).catch(() => []),
		// US-equity live paper positions (IB paper). Usually empty — trend signals are rare —
		// the home equity card shows an honest "awaiting signal" state when so.
		vps.nautilusTrades(fetch, { assetClass: 'equity', limit: 20 }).catch(() => []),
		// Semiconductor universe (real Yahoo closes) → the home "semis market pulse" card
		// derives an honest, data-driven market read from it (breadth, rotation, movers).
		vps.semiUniverse(fetch).catch(() => []),
		vps.semiGroups(fetch).catch(() => []),
		isAuthed
			? vps.backtestRuns(fetch, { limit: 500, authHeader: auth }).catch(() => [] as BacktestRun[])
			: Promise.resolve([] as BacktestRun[]),
		supabase.dcaLog(fetch, { limit: 50 }).catch(() => []),
		supabase.kolEvents(fetch, { limit: 5 }).catch(() => []),
		ohlcFor('BTC/USDT'),
		ohlcFor('ETH/USDT'),
		ohlcFor('BNB/USDT'),
		ohlcFor('SOL/USDT')
	]);

	const ohlcByCoin = { BTC: btcOhlc, ETH: ethOhlc, BNB: bnbOhlc, SOL: solOhlc };
	const stats = statsRow[0] ?? null;
	// Coerce to arrays — a malformed 200 from the API would otherwise crash the derivations
	// below (.filter/.find) and 500 the home page. Resilience over a hard fail.
	const semiUni = Array.isArray(semiUniverse) ? semiUniverse : [];
	const semiGrp = Array.isArray(semiGroups) ? semiGroups : [];
	const nautilusBTArr = Array.isArray(nautilusBT) ? nautilusBT : [];
	const equityTradesArr = Array.isArray(equityTrades) ? equityTrades : [];

	// Semis market pulse — honest facts derived from real closes; the component phrases the read.
	// No fabricated headlines: just breadth, weekly leaders/laggards, and tier rotation.
	const semiPulse = (() => {
		const u = semiUni.filter((s) => s.tier !== 'benchmark' && s.ret_1w !== null);
		if (u.length === 0) return null;
		const byWeek = [...u].sort((a, b) => (b.ret_1w ?? 0) - (a.ret_1w ?? 0));
		const upCount = u.filter((s) => (s.ret_1w ?? 0) > 0).length;
		const tiers = semiGrp
			.filter((g) => g.tier !== 'benchmark' && g.avg_ret_1m !== null)
			.sort((a, b) => (b.avg_ret_1m ?? 0) - (a.avg_ret_1m ?? 0));
		const nvda = semiUni.find((s) => s.symbol === 'NVDA') ?? null;
		const pick = (s: (typeof u)[number]) => ({
			symbol: s.symbol,
			ret_1w: s.ret_1w,
			ret_1m: s.ret_1m
		});
		return {
			total: u.length,
			up: upCount,
			leaders: byWeek.slice(0, 3).map(pick),
			laggards: byWeek.slice(-3).reverse().map(pick),
			tiers: tiers.map((g) => ({ tier: g.tier, avg_ret_1m: g.avg_ret_1m, members: g.members })),
			nvda_ret_1w: nvda?.ret_1w ?? null,
			updated_at: u[0].updated_at
		};
	})();

	// Same malformed-200 coercion as the other datasets (runs/kol/dca were the leftovers).
	const runsArr = Array.isArray(runs) ? runs : [];
	const kolArr = Array.isArray(kol) ? kol : [];
	const dcaArr = Array.isArray(dca) ? dca : [];
	const distinctStrategies = new Set(runsArr.map((r) => r.strategy).filter(Boolean));
	const distinctTimeframes = new Set(
		runsArr.map((r) => r.timeframe).filter((t): t is string => !!t)
	);

	return {
		isAuthed,
		health: {
			api: (stats?.total_runs ?? 0) > 0,
			supabase: kolArr.length > 0 || dcaArr.length > 0
		},
		summary: {
			total_runs: stats?.total_runs ?? 0,
			total_trades: stats?.total_trades ?? 0,
			distinct_strategies: stats?.distinct_strategies ?? 0,
			best_profit_pct: stats?.best_profit_pct ?? null,
			best_calmar: stats?.best_calmar ?? null,
			best_sharpe: stats?.best_sharpe ?? null,
			best_sortino: stats?.best_sortino ?? null,
			best_win_rate: stats?.best_win_rate ?? null,
			min_max_dd: stats?.min_max_dd ?? null,
			dca_count: dcaArr.length
		},
		recent_runs: runsArr.slice(0, 50),
		nautilus_backtests: nautilusBTArr,
		equity_backtests: nautilusBTArr
			.filter((b) => b.asset_class === 'equity')
			.sort((a, b) => (b.total_profit_pct ?? 0) - (a.total_profit_pct ?? 0)),
		equity_trades: equityTradesArr,
		semi_pulse: semiPulse,
		strategy_options: [...distinctStrategies].sort(),
		timeframe_options: [...distinctTimeframes].sort(),
		recent_kol: kolArr,
		recent_dca: dcaArr.slice(0, 5),
		ohlcByCoin
	};
};
