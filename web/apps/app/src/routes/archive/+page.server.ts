import type { PageServerLoad } from './$types';
import { vps } from '$lib/api';

export const load: PageServerLoad = async ({ fetch, cookies }) => {
	const jwt = cookies.get('qt_jwt');
	const auth = jwt ? `Bearer ${jwt}` : undefined;
	const runsRaw = await vps.backtestRuns(fetch, { limit: 500, authHeader: auth }).catch(() => []);
	// Coerce to array — a malformed 200 body would otherwise crash .map below.
	const runs = Array.isArray(runsRaw) ? runsRaw : [];
	const strategies = [...new Set(runs.map((r) => r.strategy))].sort();
	return { runs, strategies };
};
