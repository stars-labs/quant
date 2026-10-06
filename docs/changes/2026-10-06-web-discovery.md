# Website discovery and onboarding

Audit findings: the homepage prioritizes archived best backtests, lacks a current
house-rule overview and owner-runner path, and fetches market providers directly
from browsers. The getting-started guide omits local live execution. Seventeen
primary navigation entries compete for attention.

Acceptance: an English-default home explains research versus real accounts; an
API-backed house-rule snapshot marks missing/stale data and states fee assumptions;
a current onboarding guide explains private reporting, local authorization,
funding and stopping; six primary links retain all existing tools under More.
Remove replaced home-only components and upstream homepage fetches. Verify
aggregation/invalid/stale data, typecheck/lint, production desktop/mobile layouts,
route discovery and links. Preserve the owner-local execution boundary.

Implementation: homepage now reads only two own-API resources with bounded requests;
replaced home-only widgets, obsolete statistics clients, 108 translations and the
outdated first-login modal/store are removed. The guide covers the local runner,
private reports and eight practical questions. Hidden mobile navigation is inert,
Escape restores focus, and hosted sign-in follows the UI language.

Verification completed:

- 12 frontend logic tests pass; typecheck has zero errors and 12 existing warnings.
  Formatting and ESLint pass. Aggregation rejects missing, malformed and future
  data, and the oldest asset determines snapshot freshness.
- Production homepage values match the authoritative own-API research data.
  Refresh sends a real SvelteKit data request and updates the displayed snapshot.
- Desktop1440px and mobile390px layouts have no document overflow. Mobile hidden
  navigation is inert; Escape closes it and returns focus. All six primary links
  remain, with existing research tools retained.
- Eight guide questions expand correctly; record and account paths are reachable.
- User-reported language button failure traced to a route-level English override.
  Removed that override, translated home/guide/account/login copy with the existing
  i18n bundles and made translated arrays reactive. English remains the default;
  explicitly chosen Chinese survives reload and navigation. Both EN→中文 and
  中文→EN are verified on quant.starslab.qzz.io. Document language updates too.
- Read-only browser regression harness: `node scripts/check-language.mjs URL`.
  Production run passed: EN → 中文 → reload → guide → account → EN.
  Screenshots under `/tmp/language-zh-production-*.png` and `/tmp/web-*.png` are
  temporary evidence, not committed generated reports.
- Final Worker version: `80520e18-c698-4cf0-9aa1-52875dd228d5`.

No exchange credentials or execution commands are introduced by this change.
