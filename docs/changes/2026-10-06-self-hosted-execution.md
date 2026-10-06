# Self-hosted execution

Status: completed and verified — public runner, owner-operated HTX execution, private web/Telegram displays and hosted live retirement. Personal placement was subsequently corrected to the owner’s Oracle server; see `2026-10-06-owner-oracle-runner.md`.

The public service provides research signals and private account displays. Exchange
credentials, funding confirmations, order submission and durable order recovery belong
on the account owner's computer or server. This is an architectural boundary, not a
claim that a particular deployment satisfies every jurisdiction's regulations.

The runner uses a local SQLite journal. It records an intent before contacting an
exchange and recovers ambiguous submissions using their original client order ID.
An unknown submission must never be retried as a new order. Only confirmed monthly
funding may increase spending limits. Trend sale proceeds remain reusable; DCA uses
the current month's allocation. Fees are taken from reconciled exchange fills.

The existing Auth0 identity controls private display connections. A separate upload
token permits only submission of allowlisted account display data. The public service
must not accept exchange keys, send execution commands, or remotely enable trading.
Revoking a display token stops reporting; it does not stop the owner's executor.

Acceptance requirements:

- Public MIT source, a reproducible install command and documented local operation.
- Live trading requires explicit local configuration; dry-run is the default.
- Local restart and ambiguous-order recovery cannot duplicate purchases.
- Funding, positions and realized costs survive a restart without a platform database.
- Private display reports reject credentials, invalid values, replay and other users.
- A complete English connection flow displays freshness, fees and account holdings.
- The hosted exchange-key endpoint and its credential fields are removed.
- Tests cover accounting, restart, isolation and reporting; browser evidence covers UI.
- The personal HTX migration preserves existing holdings, funding and order IDs, with
  exactly one executor and verified account balances before live submission resumes.

Do not mark this change complete until all requirements above have evidence.

Verified implementation:

- `runner/src/starslab_runner/journal.py`: local SQLite intent and funding journal.
- `runner/src/starslab_runner/signals.py`: bounded, fresh research snapshot parsing.
- Migration 042: read-only public signal snapshot in one SQL statement.
- Migration 043: owner RLS, hashed upload-only tokens, revocation, bounded allowlisted
  reports, connection identity and monotonic sequence enforcement.
- 52 tests passed, including real PostgreSQL ownership, upload permission and hosted
  credential-retirement tests. Timeout recovery does not resubmit accepted orders.
- Migrations 042 and 043 applied to production. An independent local simulation
  fetched all 13 house assets and uploaded six simulated fills through the real HTTP
  endpoint. Anonymous account-list access returned HTTP 401.
- The wheel installs into an isolated uv tool environment, runs simulation successfully,
  contains the MIT notice and contains no credentials or account state.
- Desktop (1440px) and mobile (390px) browser fixtures show holdings, fees and stale
  reports. A 390px page has no document overflow. Configuration download contains
  only an endpoint and upload token; the create request contains only label, venue
  and report environment. Browser fixtures do not prove an actual Auth0 login.
- Web typecheck has zero errors (13 existing warnings); lint passes.
- Source removes the hosted exchange-key endpoint, component and Worker key type.
  Migration 044 is applied in production; the endpoint returns 404 and zero
  Binance credential columns remain. The Worker has no BINANCE_KEK binding.
- Public release `runner-v0.1.0` is published with wheel and source artifacts;
  both GitHub Actions runs passed. The public curl installer installed a fresh
  tool and repaired a deleted executable while preserving local configuration.
- The production website is deployed (Worker version
  `01f5123f-dcb0-4979-94de-bbb24241aff8`). A signed temporary test identity created
  a connection in the actual web UI, downloaded its token file, attached it to
  the local simulation and displayed six fills. Production desktop/mobile
  screenshots are saved under `/tmp/starslab-runner-e2e/production-*.png`.
  This verifies JWT/PostgREST integration, not interactive Auth0 provider login.
- Revoking that real connection stopped uploads while local simulation remained
  healthy. Test users, tokens and sessions were removed afterward.
- Personal HTX cutover: imported all six original client/exchange IDs, gross/net
  fill movements and confirmed 200 USDT into the local SQLite journal. Read-only
  HTX verification matches cash and each asset balance; no pending orders.
  Local live service starts healthy, reports through the production connection
  and survives a restart without additional fills. Server runtime HTX keys are
  removed; only the owner-local service can use them.

- SOCKS transport works from a freshly installed 0.1.1 wheel: the egress IP matches
  the HTX allowlist and real HTX public prices load through the user-owned SSH
  tunnel. PySocks is now an explicit dependency.

- Public transport-fix release `runner-v0.1.1` is published; its wheel returns HTTP
  200 and both corresponding GitHub Actions runs passed.

Cutover preparation and verification:

- The offline importer refuses nonempty destinations, atomically rolls back invalid
  snapshots and preserves pending identities. Historical orders without fee quotes
  retain null quotes; actual fees are derived from their reconciled movements.
- All 59 runner tests passed against disposable PostgreSQL, including operator
  report projection, chat ownership, token isolation and retirement of hosted access.
- Initial desktop units and tunnel were subsequently retired. Personal execution
  now runs as an isolated Oracle system service; see the Oracle cutover record.
- Migration045 is applied. Production privilege checks return false for anonymous
  and authenticated callers and true for the private dispatcher role. The personal
  connection receives healthy live reports with six original fills.
- NUR source commit `34f9cff` removes hosted live execution and legacy helpers;
  dotfiles `5a46fe24` selects Gate/HTX simulation only and removes all HTX key/UID
  environment configuration. Remote rebuilding runs under systemd with logs at
  `/var/tmp/starslab-owner-cutover.log`.

- Web UI labels deployed as Worker `c8b3cb26-d823-42cf-8e89-cb414aeb881c`:
  tracked equity/cash and simulation-versus-actual fees are distinguished. A
  read-only signed owner browser session displayed the real six fills and live
  report on production. Mobile (390px) has no document overflow; screenshots are
  private artifacts under `/tmp/starslab-runner-e2e/personal-live-*.png`.
  The temporary JWT and browser session were removed after verification.
- Source regression harness: 126 tests passed across simulated execution,
  Telegram reports, health checks, dispatcher and fee sensitivity. Web check has
  zero errors (13 existing warnings); lint passed. GitHub Actions run
  `37358810019` passed for source commit `fca15d8`.
- Local user lingering is enabled; both owner services are enabled and healthy.
  Authenticated BTC fee preflight returns effective 0.15% and basic 0.20%; original
  fill movements confirm actual 0.20% fees. No new orders were forced for testing.

Final deployment and boundary verification:

- Remote rebuild completed successfully, generation
  `/nix/store/rqhwg93qb3afvxkiarnk3jv8kfc8j0b8-nixos-system-oracle-arm-002-26.11.20261005.494ce7f`.
  Installed executor, dispatcher and health module hashes match all five tested
  source files. Hosted execution is active with `gate:dry_run,htx:dry_run`; both
  executor and dispatcher processes have no HTX credential/live-control variables.
  Legacy live execution modules are absent from the installed application.
- Migration046 applied: original six orders and one funding row remain private
  audit records; six derived public HTX live rows removed without fabricated sales.
  The backend role cannot select/insert old orders or confirm old funding. Real
  anonymous HTTP reads of the old public projection return an empty array.
- The installed Telegram renderer reads actual uploaded funding, cash, positions
  and reconciled fees. Dispatcher state menu version3 acknowledges a successful
  private Telegram account-summary send. Six historical fill IDs are seeded;
  subsequent reminders use reports and avoid replaying imported fills.
- Current production HTTP isolation: owner sees one healthy live report, another
  signed identity sees zero, anonymous requests return401. Temporary tokens were
  removed after this read-only check. The retired credential endpoint remains404.
- Final English login correction deployed as Worker
  `fcb70d19-9201-42ad-8375-19bc5aa20f98`: account login keeps English through the
  existing locale cookie and requests English from hosted Auth0. Browser checks
  confirm private-account copy and the actual English Auth0 sign-in page. This
  checks provider navigation, not an interactive OAuth credential exchange.
  Login screenshots are private artifacts under `/tmp/starslab-runner-e2e/`.
- Final web check: zero errors, 13 existing warnings; lint and formatting passed.
  The public installer refuses upgrades while the live service is active; its
  refusal leaves the owner runner PID and healthy state intact.

All acceptance requirements above have evidence. Local live execution remains
healthy with zero pending orders; the platform receives display-only reports.
