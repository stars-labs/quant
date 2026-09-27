# Quant Web Monorepo

SvelteKit 5 dashboard + Astro Starlight docs.

```
web/
├── pnpm-workspace.yaml
├── apps/
│   ├── app/       SvelteKit + Tailwind 4 + shadcn tokens + Layer Chart (Plotly fallback)
│   │              → https://quant.panda.qzz.io
│   └── docs/      Astro + Starlight (zh 主语 CN，Inter 字体)
│                  → https://quant.panda.qzz.io/docs/   (baked into app build)
└── packages/shared/ (reserved)
```

## Data sources (same backend as before, no changes)

```
Browser
  ├─► https://api.panda.qzz.io   (VPS PostgREST  — heavy data)
  ├─► https://auth.panda.qzz.io  (VPS GoTrue     — JWT issuer)
  ├─► https://*.supabase.co      (Supabase cloud — app events)
  └─► /(page)/+page.server.ts    (SvelteKit SSR on CF edge — merges sources)
```

VPS GoTrue shares `JWT_SECRET` with PostgREST, so the same JWT passes RLS on
`api.panda.qzz.io` natively. No token exchange needed.

## Dev

```bash
cd web
pnpm install
pnpm dev:app    # SvelteKit → http://localhost:5173
pnpm dev:docs   # Starlight → http://localhost:4321
```

Both talk to **production** APIs (no local backend needed).

## Deploy

```bash
# Requires CF account id (xiongchenyu6's):
export CLOUDFLARE_ACCOUNT_ID=2764ae0fd9a5cb92c9ac67708620e54c

pnpm deploy:app   # rebuilds (docs + reports synced in) + wrangler deploy → quant.panda.qzz.io
pnpm deploy:docs  # (no longer separate) docs are baked into app build via sync-starlight.mjs
```

## Backend integration — by feature

### Backtest HTML reports (`apps/app/static/reports/`)

`pnpm build` runs `scripts/sync-reports.mjs` which:
- Copies `../../../reports/*/` into `static/reports/`
- Writes `manifest.json` for the `/reports` listing page
- **Skips files > 20 MB** (CF Pages limit 25 MB) — writes skipped list so the
  page can show "X files skipped, migrate to R2 later"

Each folder becomes a card at `/reports`. The plotly HTML files render in-place
because they're self-contained (CDN plotly.js).

### Typed API clients (`apps/app/src/lib/api.ts`)

```ts
vps.backtestRuns(fetch, { strategy, limit })   → BacktestRun[]
vps.backtestTrades(fetch, runId)                → BacktestTrade[]
vps.ohlcAuto(fetch, pair, { from, to, maxPoints }) → { rows, source }
vps.liveTrades(fetch, { bot, limit })           → LiveTrade[]
vps.walkForward(fetch, { strategy })            → WfResult[]
supabase.kolEvents(fetch)                       → KolEvent[]
supabase.dcaLog(fetch)                          → DcaLogRow[]
```

JWT is picked up automatically from `$lib/auth.ts` if the user logged in.

### Markdown docs sync (`apps/docs/scripts/sync-docs.mjs`)

Copies selected `../../../docs/*.md` with Starlight frontmatter into the right
category folder. Edit the `MAPPING` dict in the script to add/remove.

## Auth

`$lib/auth.ts` talks to GoTrue (`auth.panda.qzz.io`):
- `login(email, pw)` → signs in
- `signup(email, pw)` → registers
- `logout()` → clears session
- `getToken()` → current valid JWT or null

Session stored in localStorage (`qt_session_v1`). Expires-in auto-tracked.

Most pages work without login (`api_anon` role). To make a route
login-only:

```sql
-- On VPS, as freeman.xiong
CREATE VIEW api.my_private AS SELECT ... FROM quant.my_table;
GRANT SELECT ON api.my_private TO authenticated;   -- NOT api_anon
GRANT SELECT ON quant.my_table TO authenticated;
NOTIFY pgrst, 'reload schema';
```

## File map (routes)

```
apps/app/src/
├── app.css                    Tailwind + theme tokens (zinc + HSL dark)
├── lib/
│   ├── api.ts                 vps / supabase clients (typed, fetch-injected)
│   ├── auth.ts                GoTrue JWT client (browser storage)
│   ├── config.ts              VITE_* env + defaults
│   ├── types.ts               all row types
│   ├── utils.ts               cn + fmtUSD / fmtPct / fmtTime
│   └── components/
│       ├── topbar.svelte      sticky glass nav + login state
│       └── kpi.svelte         KPI card (4 tones)
├── routes/
│   ├── +layout.svelte         mounts topbar + dark mode
│   ├── +page.{svelte,server.ts}  /          Hub: KPI + top 10 runs
│   ├── chart/                 /chart       BTC multi-granularity + overlay
│   ├── archive/               /archive     Backtest table + detail + equity
│   ├── wf/                    /wf          Strategy × regime matrix
│   ├── reports/               /reports     Plotly HTML report directory
│   └── login/                 /login       GoTrue signup/login
└── scripts/sync-reports.mjs   copies ../../../reports → static/reports
```

## Knobs for future

- **Custom domain**: `wrangler pages domain add quant.panda.qzz.io --project-name=quant-next`
- **KV cache layer**: uncomment in `wrangler.jsonc` after `wrangler kv namespace create qt_cache`
- **R2 for big reports**: host files > 20 MB on R2, link from manifest
- **Observability**: add `"observability": { "enabled": true }` in wrangler.jsonc
- **Realtime** (live trade push): add Supabase Realtime channel when needed
- **Per-user charts**: localStorage → KV + Durable Object after login
