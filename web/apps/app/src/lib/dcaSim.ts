// Pure DCA simulator — replay a user's monthly-budget plan against daily OHLC
// history. No I/O; caller provides rows.

import type { OhlcRow } from './types';

export type CoinSymbol = 'BTC' | 'ETH' | 'BNB' | 'SOL';
export const COIN_SYMBOLS: CoinSymbol[] = ['BTC', 'ETH', 'BNB', 'SOL'];

export interface DcaPlan {
	start_date: string; // ISO date (YYYY-MM-DD)
	monthly_usdt: number;
	/** Percentage allocation (0-100) per coin. Must sum to 100 (client enforces). */
	mix?: Partial<Record<CoinSymbol, number>>;
}

export type OhlcByCoin = Partial<Record<CoinSymbol, OhlcRow[]>>;

export interface DcaTick {
	date: string;
	invested: number;
	/** Units of each coin accumulated by end of day. */
	holdings: Partial<Record<CoinSymbol, number>>;
	/** Portfolio USD value at that day's close. */
	value: number;
	cum_invested: number;
	source: 'scheduled' | '';
}

export interface DcaSummary {
	total_invested: number;
	current_value: number;
	current_holdings: Partial<Record<CoinSymbol, number>>;
	roi_pct: number;
	n_scheduled_buys: number;
	avg_cost_by_coin: Partial<Record<CoinSymbol, number>>;
	first_date: string;
	last_date: string;
}

export interface DcaResult {
	timeline: DcaTick[];
	summary: DcaSummary;
}

function defaultMix(): Record<CoinSymbol, number> {
	return { BTC: 100, ETH: 0, BNB: 0, SOL: 0 };
}

function normalizeMix(mix: DcaPlan['mix']): Record<CoinSymbol, number> {
	const out = defaultMix();
	if (!mix) return out;
	let any = false;
	for (const c of COIN_SYMBOLS) {
		const v = Number(mix[c] ?? 0);
		if (v > 0) {
			out[c] = v;
			any = true;
		} else {
			out[c] = 0;
		}
	}
	if (!any) return defaultMix();
	const sum = COIN_SYMBOLS.reduce((s, c) => s + out[c], 0);
	if (sum <= 0) return defaultMix();
	// Rescale to 100 in case client sent non-normalized values.
	for (const c of COIN_SYMBOLS) out[c] = (out[c] / sum) * 100;
	return out;
}

function buildPriceIndex(ohlc: OhlcRow[]): Map<string, number> {
	const m = new Map<string, number>();
	for (const r of ohlc) m.set(r.bucket.slice(0, 10), r.close);
	return m;
}

export function simulateDca(plan: DcaPlan, byCoin: OhlcByCoin): DcaResult {
	const mix = normalizeMix(plan.mix);
	const priceByCoin = new Map<CoinSymbol, Map<string, number>>();
	for (const c of COIN_SYMBOLS) {
		if (byCoin[c]) priceByCoin.set(c, buildPriceIndex(byCoin[c]!));
	}

	// Union of all days across all series, for the loop. BTC history is longest.
	const allDaysSet = new Set<string>();
	for (const m of priceByCoin.values()) for (const d of m.keys()) allDaysSet.add(d);
	const allDays = [...allDaysSet].sort();
	if (allDays.length === 0) {
		return {
			timeline: [],
			summary: {
				total_invested: 0,
				current_value: 0,
				current_holdings: {},
				roi_pct: 0,
				n_scheduled_buys: 0,
				avg_cost_by_coin: {},
				first_date: plan.start_date,
				last_date: plan.start_date
			}
		};
	}

	// Scheduled days (1st of each month, snapped forward to nearest OHLC day).
	const scheduledBuyDays = new Set<string>();
	{
		const start = new Date(plan.start_date + 'T00:00:00Z');
		const end = new Date(allDays[allDays.length - 1] + 'T00:00:00Z');
		const cur = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1));
		if (cur < start) cur.setUTCMonth(cur.getUTCMonth() + 1);
		while (cur <= end) {
			const iso = cur.toISOString().slice(0, 10);
			let target = iso;
			for (let i = 0; i < 7 && !allDaysSet.has(target); i++) {
				const d = new Date(target + 'T00:00:00Z');
				d.setUTCDate(d.getUTCDate() + 1);
				target = d.toISOString().slice(0, 10);
			}
			if (allDaysSet.has(target)) scheduledBuyDays.add(target);
			cur.setUTCMonth(cur.getUTCMonth() + 1);
		}
	}

	const timeline: DcaTick[] = [];
	const holdings: Record<CoinSymbol, number> = { BTC: 0, ETH: 0, BNB: 0, SOL: 0 };
	const investedByCoin: Record<CoinSymbol, number> = { BTC: 0, ETH: 0, BNB: 0, SOL: 0 };
	let invested = 0;
	let nScheduled = 0;
	let firstDate = '';

	for (const day of allDays) {
		if (day < plan.start_date) continue;
		let dayInvested = 0;
		let source: DcaTick['source'] = '';

		if (scheduledBuyDays.has(day)) {
			// Split monthly budget across coins per mix; any coin missing a
			// quote for today is skipped (e.g. SOL pre-listing days).
			for (const c of COIN_SYMBOLS) {
				if (mix[c] <= 0) continue;
				const px = priceByCoin.get(c)?.get(day);
				if (!px) continue;
				const amt = plan.monthly_usdt * (mix[c] / 100);
				holdings[c] += amt / px;
				investedByCoin[c] += amt;
				dayInvested += amt;
			}
			if (dayInvested > 0) {
				nScheduled++;
				source = 'scheduled';
			}
		}

		invested += dayInvested;
		if (!firstDate && invested > 0) firstDate = day;

		// Portfolio value at today's close (use last-known price if a coin's
		// series gap-days, which shouldn't happen with our daily aggregates).
		let value = 0;
		for (const c of COIN_SYMBOLS) {
			const h = holdings[c];
			if (h <= 0) continue;
			const px = priceByCoin.get(c)?.get(day);
			if (px) value += h * px;
		}

		timeline.push({
			date: day,
			invested: dayInvested,
			holdings: { ...holdings },
			value,
			cum_invested: invested,
			source
		});
	}

	const last = timeline[timeline.length - 1];
	const currentValue = last?.value ?? 0;
	const avgCostByCoin: Partial<Record<CoinSymbol, number>> = {};
	for (const c of COIN_SYMBOLS) {
		if (holdings[c] > 0) avgCostByCoin[c] = investedByCoin[c] / holdings[c];
	}

	return {
		timeline,
		summary: {
			total_invested: invested,
			current_value: currentValue,
			current_holdings: { ...holdings },
			roi_pct: invested > 0 ? ((currentValue - invested) / invested) * 100 : 0,
			n_scheduled_buys: nScheduled,
			avg_cost_by_coin: avgCostByCoin,
			first_date: firstDate || plan.start_date,
			last_date: last?.date ?? plan.start_date
		}
	};
}
