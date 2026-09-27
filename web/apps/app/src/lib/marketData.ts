// Market data for the /market page.
//
// Primary source: the `market_snapshots` table (PostgREST), filled every 30 min
// by a game-box collector that stores the RAW upstream payloads. We need this
// because Binance blocks both Cloudflare Workers egress (SSR) and mainland-CN
// browsers, so direct origin fetches are dead in production.
//
// Fallback: the original direct fetches to api.binance.com / fapi.binance.com /
// api.alternative.me — still useful for non-CF local dev and as belt-and-braces
// when the snapshot is missing or stale (> 3 h).

import { CONFIG } from './config';
import { sma, macd, rsi, stochRsi, normalize } from './ta';

export interface AssetData {
	symbol: 'BTC' | 'ETH';
	price: number;
	// Technicals
	ma4y_multiple: number;
	ma5w_direction: 'up' | 'down' | 'flat';
	macd_hist: number;
	macd_cross: 'bullish' | 'bearish' | 'neutral';
	rsi_weekly: number;
	stochrsi_k: number;
	stochrsi_d: number;
	// Sentiment
	fng_value: number;
	fng_class: string;
	funding_rate_apr: number;
	// Leverage
	open_interest_usd: number;
	// Derivatives sentiment
	ls_ratio: number; // current long/short account ratio (>1 = more longs)
	ls_ratio_series: number[]; // last 48 hourly values, normalized 0–1
	taker_ratio: number; // current taker buy/sell volume ratio
	taker_ratio_series: number[]; // last 48 hourly values, normalized 0–1
	top_trader_ls: number; // top trader L/S ratio (premium metric)
	// Series for sparklines (normalized 0–1, last 30 points)
	price_series: number[];
	macd_hist_series: number[];
	rsi_series: number[];
	fng_series: number[];
	oi_series: number[];
	/** ISO timestamp of the DB snapshot the data came from; null = direct fetch. */
	snapshotTs: string | null;
}

type BinanceKline = [
	number, // openTime
	string, // open
	string, // high
	string, // low
	string, // close
	string, // volume
	...unknown[]
];

type FundingEntry = { fundingRate: string; [k: string]: unknown };
type FngEntry = { value: string; value_classification: string; timestamp: string };
type LsRatioEntry = {
	symbol: string;
	longShortRatio: string;
	longAccount: string;
	shortAccount: string;
	timestamp: number;
};
type TakerRatioEntry = { buySellRatio: string; buyVol: string; sellVol: string; timestamp: number };

/** Raw upstream responses — shared shape between the snapshot payload and the
 * direct fetches. Every key except `klines` may be null (that upstream failed). */
interface RawMarketResponses {
	klines: BinanceKline[];
	fundingRates: FundingEntry[] | null;
	oiData: { openInterest: string; symbol?: string } | null;
	fngData: { data: FngEntry[] } | null;
	lsRatioData: LsRatioEntry[] | null;
	takerRatioData: TakerRatioEntry[] | null;
	topTraderData: LsRatioEntry[] | null;
}

/** One row of quant.market_snapshots — payload keys are the raw upstream
 * responses, each null if that upstream failed during collection. */
interface MarketSnapshotRow {
	asset: string;
	ts: string;
	payload: {
		klines_1w: BinanceKline[] | null;
		funding: FundingEntry[] | null;
		open_interest: { openInterest: string; symbol?: string } | null;
		long_short: LsRatioEntry[] | null;
		taker_ratio: TakerRatioEntry[] | null;
		top_long_short: LsRatioEntry[] | null;
		fng: { data: FngEntry[] } | null;
	} | null;
}

const SNAPSHOT_MAX_AGE_MS = 3 * 60 * 60 * 1000;

async function fetchJson<T>(url: string, fetchFn: typeof fetch): Promise<T> {
	const res = await fetchFn(url);
	if (!res.ok) {
		// Cloudflare Workers warn ("A stalled HTTP response was canceled to
		// prevent deadlock") if a Response is dropped without its body being
		// read or cancelled. Cancel explicitly so the runtime releases the
		// concurrent-request slot immediately.
		await res.body?.cancel().catch(() => {});
		throw new Error(`HTTP ${res.status} for ${url}`);
	}
	return res.json() as Promise<T>;
}

/** Pure computation: raw upstream responses → AssetData. Fed by both the
 * snapshot path and the direct-fetch fallback. */
function computeAssetData(
	symbol: 'BTC' | 'ETH',
	raw: RawMarketResponses,
	snapshotTs: string | null
): AssetData {
	const { klines } = raw;
	// Mirror the original per-fetch failure defaults: ls/taker/top fall back to
	// [] (the old `.catch(() => [])`), funding falls back to [] (apr 0), fng to
	// Neutral/50, OI to 0. Only klines is hard-required (caller guarantees it).
	const fundingRates = raw.fundingRates ?? [];
	const lsRatioData = raw.lsRatioData ?? [];
	const takerRatioData = raw.takerRatioData ?? [];
	const topTraderData = raw.topTraderData ?? [];

	// --- Closes ---
	const closes = klines.map((k) => parseFloat(k[4]));
	const price = closes[closes.length - 1];

	// --- 4-Year MA Multiple (208 weeks) ---
	const sma208 = sma(closes, 208);
	const lastSma208 = sma208[sma208.length - 1];
	const ma4y_multiple = isFinite(lastSma208) && lastSma208 > 0 ? price / lastSma208 : 1;

	// --- 5-Week MA direction ---
	const sma5 = sma(closes, 5);
	const n = sma5.length - 1;
	const ma5Now = sma5[n];
	const ma5Prev = sma5[n - 1];
	let ma5w_direction: 'up' | 'down' | 'flat' = 'flat';
	if (isFinite(ma5Now) && isFinite(ma5Prev)) {
		if (ma5Now > ma5Prev * 1.001) ma5w_direction = 'up';
		else if (ma5Now < ma5Prev * 0.999) ma5w_direction = 'down';
	}

	// --- MACD ---
	const macdResult = macd(closes);
	const macd_hist = macdResult.last.hist;
	const prevHist = macdResult.hist[macdResult.hist.length - 2] ?? 0;
	let macd_cross: 'bullish' | 'bearish' | 'neutral' = 'neutral';
	if (macd_hist > 0 && prevHist <= 0) macd_cross = 'bullish';
	else if (macd_hist < 0 && prevHist >= 0) macd_cross = 'bearish';
	else if (macd_hist > 0) macd_cross = 'bullish';
	else if (macd_hist < 0) macd_cross = 'bearish';

	// --- RSI weekly ---
	const rsiValues = rsi(closes, 14);
	const rsi_weekly = rsiValues[rsiValues.length - 1] ?? 50;

	// --- StochRSI ---
	const stochResult = stochRsi(closes);
	const stochrsi_k = stochResult.k;
	const stochrsi_d = stochResult.d;

	// --- Funding rate APR ---
	let funding_rate_apr = 0;
	if (fundingRates.length > 0) {
		const avgRate =
			fundingRates.reduce((sum, f) => sum + parseFloat(f.fundingRate), 0) / fundingRates.length;
		// 3 payments/day * 365 days
		funding_rate_apr = avgRate * 3 * 365 * 100;
	}

	// --- Open Interest USD ---
	const open_interest_usd = raw.oiData ? parseFloat(raw.oiData.openInterest) * price : 0;

	// --- Fear & Greed ---
	// alternative.me is a third-party API — a 200 with an error/odd shape must not
	// throw (it would null the whole AssetData via the caller's catch).
	const fngEntries = Array.isArray(raw.fngData?.data) ? raw.fngData.data : [];
	const fngLatest = fngEntries[0];
	const fng_value = fngLatest ? parseInt(fngLatest.value, 10) : 50;
	const fng_class = fngLatest ? fngLatest.value_classification : 'Neutral';

	// --- Sparkline series (last 30, normalized) ---
	const last30closes = closes.slice(-30);
	const price_series = normalize(last30closes);

	const macdHistLast30 = macdResult.hist.slice(-30);
	const macd_hist_series = normalize(macdHistLast30);

	const rsiLast30 = rsiValues.slice(-30).map((v) => (isFinite(v) ? v : 50));
	const rsi_series = normalize(rsiLast30);

	const fngSeries = fngEntries
		.slice()
		.reverse()
		.map((f) => parseInt(f.value, 10));
	const fng_series = normalize(fngSeries.slice(-30));

	// OI series: we only have one snapshot, so build a flat series
	const oi_series = new Array(30).fill(0.5);

	// --- Derivatives sentiment ---
	// Long/Short account ratio
	const ls_ratio =
		lsRatioData.length > 0 ? parseFloat(lsRatioData[lsRatioData.length - 1].longShortRatio) : 1.0;
	const ls_ratio_raw = lsRatioData.map((e) => parseFloat(e.longShortRatio));
	const ls_ratio_series =
		ls_ratio_raw.length > 0 ? normalize(ls_ratio_raw) : new Array(48).fill(0.5);

	// Taker buy/sell ratio
	const taker_ratio =
		takerRatioData.length > 0
			? parseFloat(takerRatioData[takerRatioData.length - 1].buySellRatio)
			: 1.0;
	const taker_ratio_raw = takerRatioData.map((e) => parseFloat(e.buySellRatio));
	const taker_ratio_series =
		taker_ratio_raw.length > 0 ? normalize(taker_ratio_raw) : new Array(48).fill(0.5);

	// Top trader L/S ratio
	const top_trader_ls =
		topTraderData.length > 0
			? parseFloat(topTraderData[topTraderData.length - 1].longShortRatio)
			: 1.0;

	return {
		symbol,
		price,
		ma4y_multiple,
		ma5w_direction,
		macd_hist,
		macd_cross,
		rsi_weekly,
		stochrsi_k,
		stochrsi_d,
		fng_value,
		fng_class,
		funding_rate_apr,
		open_interest_usd,
		ls_ratio,
		ls_ratio_series,
		taker_ratio,
		taker_ratio_series,
		top_trader_ls,
		price_series,
		macd_hist_series,
		rsi_series,
		fng_series,
		oi_series,
		snapshotTs
	};
}

/** Try the DB snapshot first. Returns null when there is no usable row
 * (missing, stale, or klines absent) so the caller can fall back. */
async function fetchFromSnapshot(
	symbol: 'BTC' | 'ETH',
	fetchFn: typeof fetch
): Promise<AssetData | null> {
	const url = new URL('/market_snapshots', CONFIG.API_BASE);
	url.searchParams.set('asset', `eq.${symbol}`);
	url.searchParams.set('order', 'ts.desc');
	url.searchParams.set('limit', '1');
	const rows = await fetchJson<MarketSnapshotRow[]>(url.toString(), fetchFn);
	const row = rows[0];
	if (!row?.payload) return null;
	if (Date.now() - new Date(row.ts).getTime() > SNAPSHOT_MAX_AGE_MS) return null; // stale
	const p = row.payload;
	if (!Array.isArray(p.klines_1w) || p.klines_1w.length === 0) return null; // unusable
	return computeAssetData(
		symbol,
		{
			klines: p.klines_1w,
			fundingRates: p.funding,
			oiData: p.open_interest,
			fngData: p.fng,
			lsRatioData: p.long_short,
			takerRatioData: p.taker_ratio,
			topTraderData: p.top_long_short
		},
		row.ts
	);
}

/** Original direct-origin fetches — blocked from CF Workers / mainland CN, but
 * fine for local dev and as a fallback when the snapshot is unavailable. */
async function fetchFromOrigins(symbol: 'BTC' | 'ETH', fetchFn: typeof fetch): Promise<AssetData> {
	const binanceSymbol = symbol === 'BTC' ? 'BTCUSDT' : 'ETHUSDT';

	const [klines, fundingRates, oiData, fngData, lsRatioData, takerRatioData, topTraderData] =
		await Promise.all([
			fetchJson<BinanceKline[]>(
				`https://api.binance.com/api/v3/klines?symbol=${binanceSymbol}&interval=1w&limit=220`,
				fetchFn
			),
			fetchJson<FundingEntry[]>(
				`https://fapi.binance.com/fapi/v1/fundingRate?symbol=${binanceSymbol}&limit=7`,
				fetchFn
			),
			fetchJson<{ openInterest: string; symbol: string }>(
				`https://fapi.binance.com/fapi/v1/openInterest?symbol=${binanceSymbol}`,
				fetchFn
			),
			fetchJson<{ data: FngEntry[] }>('https://api.alternative.me/fng/?limit=30', fetchFn),
			fetchJson<LsRatioEntry[]>(
				`https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=${binanceSymbol}&period=1h&limit=48`,
				fetchFn
			).catch(() => [] as LsRatioEntry[]),
			fetchJson<TakerRatioEntry[]>(
				`https://fapi.binance.com/futures/data/takerlongshortRatio?symbol=${binanceSymbol}&period=1h&limit=48`,
				fetchFn
			).catch(() => [] as TakerRatioEntry[]),
			fetchJson<LsRatioEntry[]>(
				`https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol=${binanceSymbol}&period=1h&limit=1`,
				fetchFn
			).catch(() => [] as LsRatioEntry[])
		]);

	return computeAssetData(
		symbol,
		{ klines, fundingRates, oiData, fngData, lsRatioData, takerRatioData, topTraderData },
		null
	);
}

export async function fetchAssetData(
	symbol: 'BTC' | 'ETH',
	fetchFn: typeof fetch
): Promise<AssetData> {
	try {
		const fromSnapshot = await fetchFromSnapshot(symbol, fetchFn);
		if (fromSnapshot) return fromSnapshot;
	} catch {
		// snapshot API unreachable/broken — fall through to direct fetches
	}
	return fetchFromOrigins(symbol, fetchFn);
}
