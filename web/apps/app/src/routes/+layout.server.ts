import type { LayoutServerLoad } from './$types';
import { redirect } from '@sveltejs/kit';

// Routes behind login. Everything else (/, /dca, /login, /auth/*, /docs/*,
// /reports/* static, /api/*) stays public so the conversion funnel survives.
const PROTECTED_PREFIXES = ['/strategies', '/archive', '/chart', '/wf'];

// /reports has static HTML + an index page. Gate the index only so the funnel
// still works (users can share direct report links, but the catalog is premium).
const PROTECTED_EXACT = ['/reports', '/reports/'];

function isProtected(pathname: string): boolean {
	if (PROTECTED_EXACT.includes(pathname)) return true;
	return PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/'));
}

export const load: LayoutServerLoad = async ({ locals, cookies, url }) => {
	if (isProtected(url.pathname) && !cookies.get('qt_authed')) {
		const next = url.pathname + url.search;
		throw redirect(303, `/login?next=${encodeURIComponent(next)}`);
	}
	return { lang: locals.lang };
};
