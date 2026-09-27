// 机会雷达 thresholds and grouping. Same numbers as the Telegram digest
// (strategies/alert_dispatcher.py SCAN_*), so the page and the morning push always agree.
import type { FundingRate, OpportunityScan } from './types';

export const SCAN_NEAR = 0.03; // within 3% of the entry trigger / exit line
export const SCAN_DIP = -0.2; // 20%+ below the 30-day high
export const FUNDING_HOT = 0.2; // ≥ +20%/yr: crowded longs (carry candidates)
export const FUNDING_COLD = -0.1; // ≤ -10%/yr: crowded shorts

export const isNearEntry = (r: OpportunityScan) => r.to_entry != null && r.to_entry <= SCAN_NEAR;
export const isNearExit = (r: OpportunityScan) => r.to_exit != null && r.to_exit >= -SCAN_NEAR;
export const isDip = (r: OpportunityScan) => r.from_high_30d != null && r.from_high_30d <= SCAN_DIP;
export const fundingHeat = (f: FundingRate): 'hot' | 'cold' | null =>
	f.ann_7d >= FUNDING_HOT ? 'hot' : f.ann_7d <= FUNDING_COLD ? 'cold' : null;

// Nulls sort last whatever the direction.
const by =
	(key: (r: OpportunityScan) => number | null, dir: 1 | -1) =>
	(a: OpportunityScan, b: OpportunityScan) => {
		const x = key(a);
		const y = key(b);
		if (x == null) return y == null ? 0 : 1;
		if (y == null) return -1;
		return (x - y) * dir;
	};

export interface ScanGroups {
	/** Flat coins, closest to the buy trigger first. */
	entry: OpportunityScan[];
	/** Held coins, closest to the exit line first (to_exit is ≤ 0, so descending). */
	exit: OpportunityScan[];
	/** Every coin, deepest drop from the 30-day high first. */
	dip: OpportunityScan[];
}

export function groupScan(rows: OpportunityScan[]): ScanGroups {
	return {
		entry: rows.filter((r) => !r.held).sort(by((r) => r.to_entry, 1)),
		exit: rows.filter((r) => r.held).sort(by((r) => r.to_exit, -1)),
		dip: [...rows].sort(by((r) => r.from_high_30d, 1))
	};
}
