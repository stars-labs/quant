import type { Handle, HandleServerError } from '@sveltejs/kit';
import { normalizeLang } from '$lib/i18n';

export const handle: Handle = async ({ event, resolve }) => {
	const cookie = event.cookies.get('lang');
	const executionFlow =
		event.url.pathname === '/execution' ||
		(event.url.pathname === '/login' && event.url.searchParams.get('next') === '/execution');
	event.locals.lang = executionFlow ? 'en' : normalizeLang(cookie);
	if (executionFlow && cookie !== 'en') {
		// Keep the existing language preference through the hosted sign-in round trip.
		event.cookies.set('lang', 'en', {
			path: '/',
			httpOnly: false,
			sameSite: 'lax',
			maxAge: 365 * 24 * 60 * 60
		});
	}
	const htmlLang = event.locals.lang === 'en' ? 'en' : 'zh-CN';
	return resolve(event, {
		transformPageChunk: ({ html }) => html.replace('%lang%', htmlLang)
	});
};

// Surface SSR errors to wrangler tail with just enough context (path, error
// name, message, top of stack) to triage. Full stack + cookieKeys are
// useful when actively debugging but too noisy for steady-state logs.
export const handleError: HandleServerError = ({ error, event, status, message }) => {
	const err = error as Error;
	const stackHead = err?.stack?.split('\n').slice(0, 3).join(' | ');
	console.error(
		'[ssr-error]',
		JSON.stringify({
			path: event.url.pathname,
			status,
			errorName: err?.name,
			errorMessage: err?.message,
			stackHead
		})
	);
	return { message: message ?? 'Internal Error' };
};
