// Technical Analysis utilities — pure TypeScript, no external deps.

/** Exponential Moving Average */
export function ema(values: number[], period: number): number[] {
	if (values.length === 0 || period <= 0) return [];
	const k = 2 / (period + 1);
	const result: number[] = [];
	let prev = values[0];
	result.push(prev);
	for (let i = 1; i < values.length; i++) {
		prev = values[i] * k + prev * (1 - k);
		result.push(prev);
	}
	return result;
}

/** Simple Moving Average */
export function sma(values: number[], period: number): number[] {
	if (values.length === 0 || period <= 0) return [];
	const result: number[] = [];
	for (let i = 0; i < values.length; i++) {
		if (i < period - 1) {
			result.push(NaN);
		} else {
			let sum = 0;
			for (let j = i - period + 1; j <= i; j++) sum += values[j];
			result.push(sum / period);
		}
	}
	return result;
}

export interface MacdResult {
	line: number[];
	signal: number[];
	hist: number[];
	last: { line: number; signal: number; hist: number };
}

/** MACD (12, 26, 9) */
export function macd(closes: number[]): MacdResult {
	const fast = ema(closes, 12);
	const slow = ema(closes, 26);
	const line = fast.map((v, i) => v - slow[i]);
	const signal = ema(line, 9);
	const hist = line.map((v, i) => v - signal[i]);
	const n = hist.length - 1;
	return {
		line,
		signal,
		hist,
		last: { line: line[n], signal: signal[n], hist: hist[n] }
	};
}

/** RSI (default period = 14) */
export function rsi(closes: number[], period = 14): number[] {
	if (closes.length < period + 1) return closes.map(() => NaN);
	const result: number[] = new Array(closes.length).fill(NaN);
	let gains = 0;
	let losses = 0;
	for (let i = 1; i <= period; i++) {
		const diff = closes[i] - closes[i - 1];
		if (diff >= 0) gains += diff;
		else losses -= diff;
	}
	let avgGain = gains / period;
	let avgLoss = losses / period;
	result[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
	for (let i = period + 1; i < closes.length; i++) {
		const diff = closes[i] - closes[i - 1];
		const gain = diff > 0 ? diff : 0;
		const loss = diff < 0 ? -diff : 0;
		avgGain = (avgGain * (period - 1) + gain) / period;
		avgLoss = (avgLoss * (period - 1) + loss) / period;
		result[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
	}
	return result;
}

export interface StochRsiResult {
	k: number;
	d: number;
	series: number[];
}

/** StochRSI(3, 3, 14, 14): stochastic of RSI, then smooth K and D */
export function stochRsi(closes: number[]): StochRsiResult {
	const rsiValues = rsi(closes, 14);
	const stochPeriod = 14;
	const kSmooth = 3;
	const dSmooth = 3;

	// Raw stochastic of RSI
	const rawK: number[] = new Array(rsiValues.length).fill(NaN);
	for (let i = stochPeriod - 1; i < rsiValues.length; i++) {
		const window = rsiValues.slice(i - stochPeriod + 1, i + 1).filter((v) => !isNaN(v));
		if (window.length < stochPeriod) continue;
		const lo = Math.min(...window);
		const hi = Math.max(...window);
		rawK[i] = hi === lo ? 50 : ((rsiValues[i] - lo) / (hi - lo)) * 100;
	}

	// Smooth K
	const kSeries = sma(
		rawK.filter((v) => !isNaN(v)),
		kSmooth
	);
	// Smooth D (SMA of K)
	const dSeries = sma(kSeries, dSmooth);

	const lastK = kSeries[kSeries.length - 1] ?? 50;
	const lastD = dSeries[dSeries.length - 1] ?? 50;

	return { k: lastK, d: lastD, series: kSeries };
}

/** Normalize an array to [0, 1] range for sparkline rendering */
export function normalize(values: number[]): number[] {
	const clean = values.filter((v) => isFinite(v));
	if (clean.length === 0) return values.map(() => 0.5);
	const lo = Math.min(...clean);
	const hi = Math.max(...clean);
	if (hi === lo) return values.map(() => 0.5);
	return values.map((v) => (isFinite(v) ? (v - lo) / (hi - lo) : 0.5));
}
