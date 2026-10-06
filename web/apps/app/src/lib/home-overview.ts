import type { StrategyRecord } from './types';

export function homeOverview(input: unknown, now = Date.now()) {
	if (!Array.isArray(input) || input.length === 0) return null;
	const rows = input as StrategyRecord[];
	if (new Set(rows.map((r) => r?.asset)).size !== rows.length) return null;
	if (
		rows.some(
			(r) =>
				!r ||
				r.strategy !== 'donchian_1h' ||
				typeof r.asset !== 'string' ||
				!r.asset.trim() ||
				typeof r.start_ts !== 'string' ||
				!Number.isFinite(Date.parse(r.start_ts)) ||
				typeof r.last_ts !== 'string' ||
				!Number.isFinite(Date.parse(r.last_ts)) ||
				Date.parse(r.start_ts) > Date.parse(r.last_ts) ||
				Date.parse(r.last_ts) > now ||
				typeof r.sleeve_ret !== 'number' ||
				!Number.isFinite(r.sleeve_ret) ||
				typeof r.hold_ret !== 'number' ||
				!Number.isFinite(r.hold_ret) ||
				!Number.isInteger(r.n_closed) ||
				r.n_closed < 0
		)
	)
		return null;
	const oldest = Math.min(...rows.map((r) => Date.parse(r.last_ts!)));
	return {
		assets: rows.map((r) => r.asset),
		asOf: new Date(oldest).toISOString(),
		stale: now - oldest > 3 * 3600_000,
		start: rows.map((r) => r.start_ts!).sort()[0],
		closed: rows.reduce((sum, r) => sum + r.n_closed, 0),
		open: rows.filter((r) => r.open_entry_ts != null).length,
		modelReturn: rows.reduce((sum, r) => sum + r.sleeve_ret!, 0) / rows.length,
		holdReturn: rows.reduce((sum, r) => sum + r.hold_ret!, 0) / rows.length
	};
}
