# Self-hosted execution

Status: implementation in progress; the existing personal HTX executor remains running.

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

Verified foundation:

- `runner/src/starslab_runner/journal.py`: local SQLite intent and funding journal.
- `runner/src/starslab_runner/signals.py`: bounded, fresh research snapshot parsing.
- Migration 042: read-only public signal snapshot in one SQL statement.
- 24 tests passed, including two tests against a disposable PostgreSQL database.
  The anonymous role can retrieve the snapshot but cannot read or change source tables.
- No production migration or live executor change has been made in this phase.

Still required: exchange adapters and runner CLI, private display report connections,
web onboarding, hosted key removal, installer/release, and personal HTX migration.
