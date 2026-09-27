import type { PageServerLoad } from './$types';
import { vps } from '$lib/api';
import { groupScan } from '$lib/scan';
import type { FundingRate, MarketScanRow, OpportunityScan } from '$lib/types';

const num = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

export const load: PageServerLoad = async ({ fetch }) => {
	const [scanRaw, fundingRaw, marketRaw, stressRaw] = await Promise.all([
		vps.opportunityScan(fetch).catch(() => null),
		vps.fundingRates(fetch).catch(() => null),
		vps.marketScan(fetch).catch(() => null),
		vps.marketStress(fetch).catch(() => null)
	]);

	// Equities + commodities are their own tabs: a failure there never blanks the crypto radar
	// (and vice versa). A malformed 200 (non-array body) counts as a failure.
	const marketsFailed = !Array.isArray(marketRaw);
	const markets = (marketsFailed ? [] : marketRaw).filter(
		(r): r is MarketScanRow =>
			typeof r?.asset === 'string' &&
			(r.asset_class === 'equity' || r.asset_class === 'commodity') &&
			num(r.last_close) &&
			num(r.from_high_52w) &&
			num(r.vs_ma200)
	);
	// VIX from the hourly stress index (quant.market_stress); only shown when under a day old.
	const stress = Array.isArray(stressRaw) ? stressRaw[0] : null;
	const vixRaw = stress?.components?.vix?.raw;
	const vixFresh = stress && Date.now() - new Date(stress.ts).getTime() < 86_400_000;
	const vix = num(vixRaw) && vixFresh ? { value: vixRaw, ts: stress.ts } : null;
	const marketPart = { markets, marketsFailed, vix };

	// Both or nothing, as on /record: a failed request or a malformed 200 (non-array body) from
	// EITHER crypto view shows the error state, never half a radar that reads as "nothing to see".
	if (!Array.isArray(scanRaw) || !Array.isArray(fundingRaw)) {
		return { scan: [], groups: groupScan([]), funding: [], failed: true, ...marketPart };
	}
	const scan = scanRaw.filter(
		(r): r is OpportunityScan => typeof r?.asset === 'string' && typeof r.held === 'boolean'
	);
	const funding = fundingRaw
		.filter((f): f is FundingRate => typeof f?.asset === 'string' && Number.isFinite(f.ann_7d))
		.sort((a, b) => b.ann_7d - a.ann_7d);
	return { scan, groups: groupScan(scan), funding, failed: false, ...marketPart };
};
