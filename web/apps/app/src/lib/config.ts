// Public runtime config.
// On Cloudflare Pages these would come from `[vars]` at build time via Vite's
// import.meta.env. Vite requires VITE_ prefix for client exposure.

export const CONFIG = {
	API_BASE: import.meta.env.VITE_API_BASE ?? 'https://api.panda.qzz.io',
	// Auth0 (Universal Login). Domain/client id come from the Auth0 dashboard;
	// audience must match the Auth0 API identifier AND PostgREST's jwt-aud.
	AUTH0_DOMAIN: import.meta.env.VITE_AUTH0_DOMAIN ?? 'autolife.jp.auth0.com',
	AUTH0_CLIENT_ID: import.meta.env.VITE_AUTH0_CLIENT_ID ?? '8aAbuMhZlFa94TbPozNZIKSxfSlv0B4r',
	AUTH0_AUDIENCE: import.meta.env.VITE_AUTH0_AUDIENCE ?? 'https://api.panda.qzz.io',
	SUPABASE_URL: import.meta.env.VITE_SUPABASE_URL ?? 'https://rhweqsxothaezsbxjwaj.supabase.co',
	SUPABASE_ANON:
		import.meta.env.VITE_SUPABASE_ANON ?? 'sb_publishable_RRSWxhXvvaUqk3S9nF7m9A_loMqoxxw'
};

export const DEFAULT_PAIRS = [
	'BTC/USDT',
	'ETH/USDT',
	'BNB/USDT',
	'SOL/USDT',
	'XRP/USDT',
	'DOGE/USDT'
];

// Affiliate links — empty string hides the CTA. Override per-deploy via
// VITE_BINANCE_REF / VITE_OKX_REF in wrangler.jsonc → vars.
export const AFFILIATE = {
	BINANCE_REF_URL: import.meta.env.VITE_BINANCE_REF ?? '',
	OKX_REF_URL: import.meta.env.VITE_OKX_REF ?? '',
	GITHUB_URL: 'https://github.com/xiongchenyu6/freqtrade-strategies'
};
