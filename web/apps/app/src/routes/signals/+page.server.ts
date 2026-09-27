import type { PageServerLoad } from './$types';
import { vps } from '$lib/api';

export const load: PageServerLoad = async ({ fetch, cookies }) => {
	const jwt = cookies.get('qt_jwt');
	const auth = jwt ? `Bearer ${jwt}` : undefined;
	const [runs, news] = await Promise.all([
		vps.backtestRuns(fetch, { limit: 100, authHeader: auth }).catch(() => []),
		vps.newsItems(fetch, { limit: 60 }).catch(() => [])
	]);
	return { runs, news: Array.isArray(news) ? news : [] };
};
