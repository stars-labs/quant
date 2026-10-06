# Personal Oracle execution

The owner clarified that the personal executor belongs on the owner's Oracle
server. "Local" denotes owner-operated execution, not a daily-desktop requirement.
The earlier game-box placement allowed suspend/power-off gaps.

A separate NixOS `owner-starslab-runner.service` now runs on oracle-arm-002,
using the dedicated `starslab-runner` OS user and private state directory
`/var/lib/starslab-runner`. Website/collector processes cannot read its credentials.
The public execution service remains Gate/HTX simulation only. This personal service
runs only the owner's account; other users deploy their own executors.

Verified:

- Rebuild succeeded; current generation
  `/nix/store/4a9v8z066pd4jv3qrzfpyajm13wr2w3v-nixos-system-oracle-arm-002-26.11.20261005.494ce7f`.
- Direct Oracle HTTPS egress authenticates the configured HTX account and matches
  its existing IP allowlist; no desktop SSH tunnel is needed.
- Desktop stopped before consistent SQLite backup. Exact comparison preserves all
  seven client/action/position/exchange IDs and gross/net movements. Confirmed
  monthly funding remains trend100/DCA100; no pending orders.
- Oracle starts and survives configuration activation with `healthy, pending=0`;
  no extra fills during cutover. Website report and Telegram acknowledgement
  contain the same seven fills.
- Collector OS user cannot read private credentials. Desktop credentials and
  display token removed after verified takeover.
- Retired desktop units/tunnel removed; desktop configuration is simulation-only,
  while the previous live journal remains a private inactive archive.
- Health checks require the owner Oracle system service, not retired desktop units.
  Canonical/vendored health sources match; focused regression tests pass.

NUR source `709668e`; Oracle dotfiles `5451df51`. The NixOS module vendors canonical
runner sources and their license; keep those copies synchronized. Owner-approved
temporary private credentials remain until the owner updates SOPS. No credentials
or generated journals are committed.
