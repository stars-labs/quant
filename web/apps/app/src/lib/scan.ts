// 机会雷达 thresholds and grouping. Same numbers as the Telegram digest
// (strategies/alert_dispatcher.py SCAN_*), so the page and the morning push always agree.
import type { FundingRate, MarketScanRow, OpportunityScan } from './types';

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

// US equities + commodities (api.market_scan). Same numbers as strategies/market_scan.py
// NEAR_HIGH / DEEP_DD (the Telegram digest). Observations only: the daily breakout rule lost to
// buy-and-hold out of sample on these assets (scripts/screen_daily_breakout.py).
export const NEAR_HIGH = -0.02; // within 2% of the 52-week closing high
export const DEEP_DD = -0.3; // 30%+ below the 52-week closing high

export const isNearHigh = (r: MarketScanRow) => r.from_high_52w >= NEAR_HIGH;
export const isDeep = (r: MarketScanRow) => r.from_high_52w <= DEEP_DD;

export interface MarketSummary {
	rows: MarketScanRow[];
	nearHigh: number;
	deep: number;
	/** Closing above the 200-day average, out of rows.length. */
	aboveMa: number;
}

/** One asset class, closest to its 52-week high first. */
export function summarizeMarket(
	rows: MarketScanRow[],
	cls: MarketScanRow['asset_class']
): MarketSummary {
	const mine = rows
		.filter((r) => r.asset_class === cls)
		.sort((a, b) => b.from_high_52w - a.from_high_52w);
	return {
		rows: mine,
		nearHigh: mine.filter(isNearHigh).length,
		deep: mine.filter(isDeep).length,
		aboveMa: mine.filter((r) => r.vs_ma200 > 0).length
	};
}
