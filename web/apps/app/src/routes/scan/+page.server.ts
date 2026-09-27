import type { PageServerLoad } from './$types';
import { vps } from '$lib/api';
import { groupScan } from '$lib/scan';
import type { FundingRate, OpportunityScan } from '$lib/types';

export const load: PageServerLoad = async ({ fetch }) => {
	const [scanRaw, fundingRaw] = await Promise.all([
		vps.opportunityScan(fetch).catch(() => null),
		vps.fundingRates(fetch).catch(() => null)
	]);
	// Both or nothing, as on /record: a failed request or a malformed 200 (non-array body) from
	// EITHER view shows the error state, never half a radar that reads as "nothing to see".
	if (!Array.isArray(scanRaw) || !Array.isArray(fundingRaw)) {
		return { scan: [], groups: groupScan([]), funding: [], failed: true };
	}
	const scan = scanRaw.filter(
		(r): r is OpportunityScan => typeof r?.asset === 'string' && typeof r.held === 'boolean'
	);
	const funding = fundingRaw
		.filter((f): f is FundingRate => typeof f?.asset === 'string' && Number.isFinite(f.ann_7d))
		.sort((a, b) => b.ann_7d - a.ann_7d);
	return { scan, groups: groupScan(scan), funding, failed: false };
};
