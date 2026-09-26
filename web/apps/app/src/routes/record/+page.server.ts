import type { PageServerLoad } from './$types';
import { vps } from '$lib/api';
import type { StrategyRecord, StrategyTrade } from '$lib/types';

// Portfolio view of api.strategy_record. The view is the single source of truth for every
// stat; here we only average across assets (equal-weight, no rebalancing), exactly as the
// Telegram scorecard and the daily report do.
export interface RecordSummary {
	assets: string[];
	startTs: string;
	asOf: string | null;
	portfolioRet: number;
	holdRet: number;
	nClosed: number;
	nWins: number;
	nOpen: number;
	winRate: number | null;
	best: { asset: string; ret: number } | null;
	nLive: number;
	nBackfilled: number;
	// When the backfill ran = when live recording began; everything before is replayed history.
	liveSince: string | null;
}

const avg = (xs: number[]) => xs.reduce((s, x) => s + x, 0) / xs.length;

function summarize(record: StrategyRecord[], trades: StrategyTrade[]): RecordSummary | null {
	// An asset only counts once the backfill has set its baseline (start_*) and a last close.
	const rows = record.filter(
		(r) => r.start_ts != null && r.sleeve_ret != null && r.hold_ret != null
	);
	if (rows.length === 0) return null;
	const nClosed = rows.reduce((s, r) => s + (r.n_closed ?? 0), 0);
	const nWins = rows.reduce((s, r) => s + (r.n_wins ?? 0), 0);
	let best: RecordSummary['best'] = null;
	for (const r of rows) {
		if (r.best_ret != null && (best == null || r.best_ret > best.ret))
			best = { asset: r.asset, ret: r.best_ret };
	}
	const backfilled = trades.filter((t) => !t.live);
	return {
		assets: rows.map((r) => r.asset),
		startTs: rows.map((r) => r.start_ts!).sort()[0],
		asOf:
			rows
				.map((r) => r.last_ts)
				.filter((v): v is string => v != null)
				.sort()
				.at(-1) ?? null,
		portfolioRet: avg(rows.map((r) => r.sleeve_ret!)),
		holdRet: avg(rows.map((r) => r.hold_ret!)),
		nClosed,
		nWins,
		nOpen: rows.filter((r) => r.open_entry_ts != null).length,
		winRate: nClosed > 0 ? nWins / nClosed : null,
		best,
		nLive: trades.length - backfilled.length,
		nBackfilled: backfilled.length,
		liveSince:
			backfilled
				.map((t) => t.created_at)
				.sort()
				.at(-1) ?? null
	};
}

export const load: PageServerLoad = async ({ fetch }) => {
	const [recordRaw, tradesRaw] = await Promise.all([
		vps.strategyRecord(fetch).catch(() => null),
		vps.strategyTrades(fetch).catch(() => null)
	]);
	// Both or nothing. The stats come from strategy_record, the backfilled/live split and the
	// history from strategy_trades: rendering one without the other shows a false "0
	// backfilled" or a trade table under an error box. So a failed request, or a malformed 200
	// (non-array body, same class as /nautilus), from EITHER shows the error state instead of
	// an honest "not started yet" empty state.
	if (!Array.isArray(recordRaw) || !Array.isArray(tradesRaw)) {
		return { record: [], trades: [], summary: null, failed: true };
	}
	const record = recordRaw.filter((r): r is StrategyRecord => typeof r?.asset === 'string');
	const trades = tradesRaw.filter(
		(t): t is StrategyTrade => typeof t?.asset === 'string' && t.entry_price != null
	);
	return { record, trades, summary: summarize(record, trades), failed: false };
};
