import type { PageServerLoad } from './$types';
import { vps } from '$lib/api';
import { homeOverview } from '$lib/home-overview';

export const load: PageServerLoad = async ({ fetch }) => {
	// Keep the public landing page usable when the data service is unavailable.
	const read: typeof fetch = (input, init) =>
		fetch(input, { ...init, signal: AbortSignal.timeout(8000) });
	const [record, stress] = await Promise.all([
		vps.strategyRecord(read).catch(() => null),
		vps.marketStress(read).catch(() => null)
	]);
	const market = Array.isArray(stress) ? stress[0] : null;
	return {
		overview: homeOverview(record),
		market:
			market &&
			typeof market.ts === 'string' &&
			Number.isFinite(market.stress_score) &&
			market.stress_score >= 0 &&
			market.stress_score <= 100 &&
			Number.isFinite(Date.parse(market.ts)) &&
			Date.parse(market.ts) <= Date.now()
				? {
						score: market.stress_score,
						asOf: market.ts,
						stale: Date.now() - Date.parse(market.ts) > 3 * 3600_000
					}
				: null
	};
};
