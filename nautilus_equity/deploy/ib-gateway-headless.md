# Headless IB Gateway sidecar (oracle-amd-001)

The US-equity engine needs a logged-in **IB Gateway** to pull data and (later) trade paper.
Gateway is an x86_64 GUI Java app with **no real headless mode** and no nixpkgs package, so we
run it as a container on the fleet's existing x86_64 box and reach it over the WireGuard mesh.

```
oracle-amd-001 (x86_64, NixOS)                         oracle-arm-002 / local box
┌──────────────────────────────────────┐
│ podman: ghcr.io/gnzsnz/ib-gateway     │   wg0 (trusted)   nautilus_equity
│   Gateway + IBC + Xvfb + VNC          │◄─────────────────  download_ib.py (now)
│   API bound 172.22.240.104:4002 only  │   172.22.240.104   live equity node (later)
└──────────────────────────────────────┘      :4002
```

Why a container, not a Nix derivation: nixpkgs has no IB Gateway/TWS package; IBKR's install4j
installer URL+hash rotates every release, so a hand-rolled `buildFHSEnv` breaks constantly. The
`gnzsnz/ib-gateway` image bundles Gateway+IBC+Xvfb+VNC and tracks those bumps. It stays declarative
+ sops on NixOS via `virtualisation.oci-containers`.

## Files
- `dotfiles/nixos-configurations/oracle-amd-001/ib-gateway.nix` — the podman service + sops env.
- imported from that host's `default.nix`.

## One-time setup (you — these can't be automated)
1. **Disable 2FA on the paper login.** IBKR portal → Settings → User Settings → Secure Login
   System → exclude the paper user. Without this the container blocks on a phone prompt every
   daily restart. (Paper only — never do this for a live account.)
2. **Add the paper credentials to sops** (encrypted; never plaintext in the repo):
   ```
   cd ~/dotfiles && sops secrets/common.yaml
   # add at top level:
   #   ib-gateway:
   #     username: <paper user>
   #     password: <paper password>
   ```
   ⚠️ The password shared in chat should be **rotated** in the IBKR portal before going live.
3. **Deploy** (build locally — amd-001 has only ~1 GB RAM, never build on it):
   ```
   cd ~/dotfiles
   nixos-rebuild switch --flake .#oracle-amd-001 --target-host root@oracle-amd-001
   ```
4. **Verify login** (first run): temporarily uncomment the VNC port line in `ib-gateway.nix`,
   set `VNC_SERVER_PASSWORD` in the sops env, redeploy, and VNC to `172.22.240.104:5900` over the
   mesh to watch IBC log in. Re-comment when green.

## Verify the API is reachable (from any mesh host)
```
nc -vz 172.22.240.104 4002          # socket open?
P=nautilus_equity/.venv/bin/python
IB_HOST=172.22.240.104 IB_PORT=4002 $P nautilus_equity/download_ib.py
# → 3y adjusted daily+hourly bars for NVDA/AMD/QQQ into nautilus_equity/catalog/
```
`download_ib.py` defaults to `IB_PORT=4002` already; set `IB_HOST` to the mesh IP when running
off-box (it defaults to `127.0.0.1`).

## Gotchas
- **Port mapping:** confirm `4002:4002` against the pinned image tag's README — the image has
  exposed the API through a socat relay and the published port has varied across versions.
- **Daily restart:** `AUTO_RESTART_TIME=11:59 PM America/New_York` restarts Gateway outside US
  RTH without re-auth. Don't schedule it during market hours.
- **Read-only:** `READ_ONLY_API=yes` blocks order placement — correct for data/reconcile. Flip to
  `no` only at Stage 4 (paper execution), and keep `TRADING_MODE=paper`.
- **Never public:** the API is bound to the wg IP and `wg0` is a trusted firewall interface — do
  not add 4002 to `allowedTCPPorts` or bind `0.0.0.0`.
