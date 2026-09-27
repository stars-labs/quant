// Lightweight first-party analytics — fire-and-forget POSTs to the write-only
// api.web_events_in view (PostgREST, anon-writable; we attach the Bearer token
// when logged in so the row gets the authenticated role). Mirrors alerts.ts
// for CONFIG.API_BASE/getToken usage. Tracking must NEVER block or break the
// UI: every entry point is SSR-safe and swallows all errors.
//
// Attribution (migration 037, web_events.campaign): links we send carry ?ref=<channel>
// (tg_entry, tg_scan, …). A page_view records the ref of the URL it landed on; every other
// event (signup, telegram_bound, …) records the browser's FIRST-touch ref, kept in
// localStorage, so a bind can be credited to the push that brought the visitor in.
import { get } from 'svelte/store';
import { browser } from '$app/environment';
import { CONFIG } from './config';
import { getToken, session } from './auth';
import { REF_RE, refFromSearch } from './growth';

/** The only event names the backend accepts. */
export type TrackEvent =
	'page_view' | 'signup' | 'backtest_submit' | 'signal_create' | 'telegram_bound';

const VID_KEY = 'qt_vid';
/** localStorage — the first ?ref= this browser arrived with (never overwritten). */
const FIRST_REF_KEY = 'qt_first_ref';
/** sessionStorage flag — `ref` is sent only on the first event of a session. */
const REF_SENT_KEY = 'qt_ref_sent';
/** sessionStorage map {path: epoch_ms} — page_view de-dupe window per path. */
const PV_TS_KEY = 'qt_pv_ts';
const PV_WINDOW_MS = 30_000;

function uuid(): string {
	if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function')
		return crypto.randomUUID();
	// Insecure-context fallback (crypto.randomUUID needs https/localhost).
	return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
		const r = (Math.random() * 16) | 0;
		return (c === 'x' ? r : (r & 3) | 8).toString(16);
	});
}

/** Stable anonymous visitor id, persisted in localStorage. '' on SSR. */
export function visitorId(): string {
	if (!browser) return '';
	try {
		let v = localStorage.getItem(VID_KEY);
		if (!v) {
			v = uuid();
			localStorage.setItem(VID_KEY, v);
		}
		return v;
	} catch {
		// localStorage unavailable (private mode etc.) — still report, unkeyed.
		return '';
	}
}

/** At most one page_view per path per 30s (sessionStorage timestamp map). */
function shouldSendPageView(path: string): boolean {
	try {
		const map: Record<string, number> = JSON.parse(sessionStorage.getItem(PV_TS_KEY) ?? '{}');
		const now = Date.now();
		if (map[path] && now - map[path] < PV_WINDOW_MS) return false;
		map[path] = now;
		sessionStorage.setItem(PV_TS_KEY, JSON.stringify(map));
		return true;
	} catch {
		return true;
	}
}

/** Referrer host, only on the FIRST event of this session; null otherwise. */
function firstEventRef(): string | null {
	try {
		if (sessionStorage.getItem(REF_SENT_KEY)) return null;
		sessionStorage.setItem(REF_SENT_KEY, '1');
		return document.referrer ? new URL(document.referrer).host : null;
	} catch {
		return null;
	}
}

/** The URL's own ?ref=, remembered as the first touch when this browser has none yet. */
function landingRef(): string | null {
	try {
		const r = refFromSearch(location.search);
		if (r && !localStorage.getItem(FIRST_REF_KEY)) localStorage.setItem(FIRST_REF_KEY, r);
		return r;
	} catch {
		return null;
	}
}

function firstTouchRef(): string | null {
	try {
		const r = localStorage.getItem(FIRST_REF_KEY);
		return r && REF_RE.test(r) ? r : null;
	} catch {
		return null;
	}
}

/** campaign column: the landing URL's ref on page_view, the first-touch ref otherwise. */
function campaignFor(event: TrackEvent): string | null {
	const here = landingRef();
	return event === 'page_view' ? here : firstTouchRef();
}

/**
 * Record an analytics event. Fire-and-forget: returns immediately, never
 * throws, never blocks the UI, no-op during SSR.
 */
export function track(event: TrackEvent, path?: string): void {
	if (!browser) return;
	try {
		const p = path ?? location.pathname;
		// Before the de-dupe: a landing ?ref= must be remembered even if this view is dropped.
		const campaign = campaignFor(event);
		if (event === 'page_view' && !shouldSendPageView(p)) return;

		const body: Record<string, unknown> = { event, path: p, visitor: visitorId() };
		const uid = get(session)?.user?.sub;
		if (uid) body.user_id = uid;
		// hooks.server.ts sets <html lang> from the `lang` cookie (en | zh-CN).
		const lang = document.documentElement.lang || navigator.language;
		if (lang) body.lang = lang;
		const ref = firstEventRef();
		if (ref) body.ref = ref;
		if (campaign) body.campaign = campaign;

		const headers: Record<string, string> = { 'Content-Type': 'application/json' };
		const t = getToken();
		if (t) headers.Authorization = `Bearer ${t}`;

		void fetch(`${CONFIG.API_BASE}/web_events_in`, {
			method: 'POST',
			headers,
			body: JSON.stringify(body),
			keepalive: true // survives navigations
		}).catch(() => {});
	} catch {
		// Analytics must never break the app.
	}
}
