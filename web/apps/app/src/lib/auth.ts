// Auth0 client — thin wrapper around @auth0/auth0-spa-js that keeps the old
// GoTrue-era contract intact: a synchronous getToken(), a `session` store,
// and the qt_authed/qt_jwt cookies the SSR loads read. Runs client-side only.
import { writable, derived, type Readable } from 'svelte/store';
import { browser } from '$app/environment';
import { createAuth0Client, type Auth0Client } from '@auth0/auth0-spa-js';
import { CONFIG } from './config';

/** Namespace for the custom claims the Auth0 post-login Action injects.
 * `uid` is the stable per-user UUID (legacy GoTrue id for migrated users) —
 * it is what RLS's auth.uid() reads and what we expose as `user.sub`. */
const NS = 'https://panda.qzz.io';

export interface Session {
	access_token: string;
	refresh_token: string; // unused with Auth0 (SDK manages rotation) — kept for shape compat
	expires_at: number; // epoch ms
	user: { sub?: string; email?: string; role?: string };
}

const KEY = 'qt_session_v1';
/** Cookie the gate reads — route access flag. */
const GATE_COOKIE = 'qt_authed';
/** Cookie the SSR server reads to call PostgREST on behalf of the user.
 * Scoped to the same origin as the worker; PostgREST is on a different
 * subdomain so this cookie is not sent to it directly — SvelteKit SSR
 * reads it and re-emits as a Bearer header when proxying. */
const JWT_COOKIE = 'qt_jwt';

function setAuthCookies(token: string, maxAgeSec: number) {
	if (!browser) return;
	const attrs =
		`path=/; max-age=${maxAgeSec}; SameSite=Lax` +
		(location.protocol === 'https:' ? '; Secure' : '');
	document.cookie = `${GATE_COOKIE}=1; ${attrs}`;
	document.cookie = `${JWT_COOKIE}=${token}; ${attrs}`;
}
function clearAuthCookies() {
	if (!browser) return;
	document.cookie = `${GATE_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
	document.cookie = `${JWT_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
}

function loadInitial(): Session | null {
	if (!browser) return null;
	try {
		const raw = localStorage.getItem(KEY);
		return raw ? (JSON.parse(raw) as Session) : null;
	} catch {
		return null;
	}
}

const initialSession = loadInitial();
export const session = writable<Session | null>(initialSession);

export const user: Readable<Session['user'] | null> = derived(session, ($s) => $s?.user ?? null);

export function getToken(): string | null {
	if (!browser) return null;
	// Primary: localStorage session (kept fresh by the silent-sync timer).
	const raw = localStorage.getItem(KEY);
	if (raw) {
		try {
			const s: Session = JSON.parse(raw);
			if (Date.now() < s.expires_at) return s.access_token;
		} catch {
			// fall through to cookie
		}
	}
	// Fallback: qt_jwt cookie. Lets API calls succeed when localStorage was
	// cleared but the cookie is still live — without this, /chart's onMount
	// fetch goes anon and gets 401 from auth-only views (ohlc_1h_recent, etc.).
	const m = document.cookie.match(/(?:^|;\s*)qt_jwt=([^;]+)/);
	return m ? decodeURIComponent(m[1]) : null;
}

function persist(s: Session | null) {
	if (!browser) return;
	if (s) localStorage.setItem(KEY, JSON.stringify(s));
	else localStorage.removeItem(KEY);
}

function decodeJwt<T = Record<string, unknown>>(tok: string): T | null {
	try {
		const [, p] = tok.split('.');
		return JSON.parse(atob(p.replace(/-/g, '+').replace(/_/g, '/')));
	} catch {
		return null;
	}
}

// --- Auth0 SDK ------------------------------------------------------------

let _client: Promise<Auth0Client> | null = null;

function client(): Promise<Auth0Client> {
	if (!browser) throw new Error('auth0 client is browser-only');
	if (!CONFIG.AUTH0_DOMAIN || !CONFIG.AUTH0_CLIENT_ID) {
		throw new Error('Auth0 not configured (VITE_AUTH0_DOMAIN / VITE_AUTH0_CLIENT_ID)');
	}
	_client ??= createAuth0Client({
		domain: CONFIG.AUTH0_DOMAIN,
		clientId: CONFIG.AUTH0_CLIENT_ID,
		// localstorage (not memory) so a hard reload can silently restore the
		// session without a round-trip to Auth0.
		cacheLocation: 'localstorage',
		useRefreshTokens: true,
		authorizationParams: {
			audience: CONFIG.AUTH0_AUDIENCE,
			scope: 'openid profile email offline_access',
			redirect_uri: `${location.origin}/auth/callback`
		}
	});
	return _client;
}

/** Pull a fresh access token out of the SDK (silent renew via rotating
 * refresh token when needed) and mirror it into the legacy sync stores:
 * localStorage session + qt_authed/qt_jwt cookies. */
async function syncFromAuth0(): Promise<Session> {
	const c = await client();
	const token = await c.getTokenSilently({ detailedResponse: true });
	if (!token) {
		throw new Error('Auth0 returned no token during silent authentication');
	}
	const { access_token, expires_in } = token;
	const payload = decodeJwt<Record<string, string>>(access_token) ?? {};
	const expiresIn = expires_in ?? 3600;
	const s: Session = {
		access_token,
		refresh_token: '',
		expires_at: Date.now() + expiresIn * 1000,
		// `sub` deliberately carries the namespaced uid (stable UUID), not the
		// Auth0 `auth0|…` subject — downstream code and RLS key on the UUID.
		user: {
			sub: payload[`${NS}/uid`],
			email: payload[`${NS}/email`],
			role: payload[`${NS}/role`]
		}
	};
	persist(s);
	session.set(s);
	setAuthCookies(access_token, expiresIn);
	scheduleSync(s);
	return s;
}

/** Local-only teardown (no Auth0 redirect) — used when silent renew fails. */
function localLogout() {
	persist(null);
	session.set(null);
	clearAuthCookies();
	clearSyncTimer();
}

export function logout() {
	localLogout();
	if (!browser) return;
	// Also end the Auth0 session so the next loginWithRedirect shows the
	// account picker instead of silently signing back in.
	void client()
		.then((c) => c.logout({ logoutParams: { returnTo: location.origin } }))
		.catch(() => {
			/* Auth0 unreachable — local state is already cleared */
		});
}

// --- Silent refresh ------------------------------------------------------
// Access tokens are 1h; we swap them ~5 min before expiry so a user with a
// tab open never sees a 401-and-bounce. The SDK serialises concurrent
// getTokenSilently calls and handles refresh-token rotation internally.

const REFRESH_MARGIN_MS = 5 * 60 * 1000;
let syncTimer: ReturnType<typeof setTimeout> | null = null;

function clearSyncTimer() {
	if (syncTimer) {
		clearTimeout(syncTimer);
		syncTimer = null;
	}
}

function scheduleSync(s: Session) {
	if (!browser) return;
	clearSyncTimer();
	const delay = Math.max(0, s.expires_at - Date.now() - REFRESH_MARGIN_MS);
	syncTimer = setTimeout(() => void trySync(), delay);
}

async function trySync(): Promise<void> {
	try {
		await syncFromAuth0();
	} catch (e) {
		const code = (e as { error?: string }).error;
		if (code === 'login_required' || code === 'consent_required' || code === 'invalid_grant') {
			// Session is truly gone — clean local state so the gate bounces the
			// user to /login?next=... on next navigation. No Auth0 redirect from
			// a background timer.
			localLogout();
			return;
		}
		// Transient failure (network blip, Auth0 hiccup) — retry in 60s.
		syncTimer = setTimeout(() => void trySync(), 60_000);
	}
}

// Boot: resume the sync cycle if we have a live session, or quietly try to
// restore one from the SDK cache (e.g. localStorage `qt_session_v1` was
// cleared but the Auth0 cache survived).
if (browser && CONFIG.AUTH0_DOMAIN) {
	if (initialSession) scheduleSync(initialSession);
	else void trySync();
}

// --- Universal Login ------------------------------------------------------
// All flows redirect to the Auth0 hosted page (Authorization Code + PKCE) and
// come back to /auth/callback, which calls handleAuthCallback().

async function redirectToLogin(next?: string, extra?: Record<string, string>) {
	const c = await client();
	await c.loginWithRedirect({
		appState: { next: next ?? '/' },
		authorizationParams: { ...extra }
	});
}

export function login(next?: string) {
	if (!browser) return;
	void redirectToLogin(next);
}

export function signup(next?: string) {
	if (!browser) return;
	void redirectToLogin(next, { screen_hint: 'signup' });
}

export function loginWithGoogle(next?: string) {
	if (!browser) return;
	void redirectToLogin(next, { connection: 'google-oauth2' });
}

/**
 * Finish the Authorization Code + PKCE round-trip on /auth/callback: exchange
 * the ?code for tokens, mirror them into the legacy stores, and return the
 * same-origin path to continue to. Throws on Auth0 errors (?error=...).
 */
export async function handleAuthCallback(): Promise<{ next: string }> {
	const c = await client();
	const { appState } = await c.handleRedirectCallback<{ next?: string }>();
	await syncFromAuth0();
	const rawNext = appState?.next ?? '/';
	const next = rawNext.startsWith('/') && !rawNext.startsWith('//') ? rawNext : '/';
	// Clean ?code=&state= out of the URL bar.
	history.replaceState(null, '', location.pathname);
	return { next };
}
