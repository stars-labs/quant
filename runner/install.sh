#!/bin/sh
set -eu

# Installs executable code only. Local credentials, journals and enable settings
# are preserved. No service is started and no live permission is granted here.
case "$(uname -s)" in
  Linux|Darwin) ;;
  *) echo 'Use Linux or macOS (Windows users can use WSL2).' >&2; exit 1 ;;
esac

if ! command -v uv >/dev/null 2>&1; then
  curl -fsSL https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"
  export PATH
fi

runner_home="${STARSLAB_RUNNER_HOME:-$HOME/.config/starslab-runner}"
if command -v systemctl >/dev/null 2>&1 && systemctl --user is-active --quiet starslab-runner.service; then
  echo 'Stop your runner with systemctl --user stop starslab-runner before upgrading.' >&2
  exit 1
fi

if command -v systemctl >/dev/null 2>&1; then
  for unit in starslab-runner.service owner-starslab-runner.service; do
    if systemctl is-active --quiet "$unit" || systemctl --user is-active --quiet "$unit"; then
      echo "Stop $unit before reinstalling." >&2
      exit 1
    fi
  done
fi

# Hold both journal locks while replacing executable code. Python is provided by uv.
uv run --no-project --python 3.13 python - "$runner_home" <<'PYTHON'
import fcntl, os, pathlib, subprocess, sys
# Linux foreground executors can use another --home. Inspect only our UID's
# process arguments and report no paths, credentials or argument contents.
proc = pathlib.Path('/proc')
if proc.exists():
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            args = (entry/'cmdline').read_bytes().split(b'\0')
            names = [pathlib.Path(os.fsdecode(arg)).name for arg in args[:3] if arg]
            module = any(args[index:index+2] == [b'-m', b'starslab_runner']
                         for index in range(len(args)-1))
            if 'starslab-runner' in names or module:
                raise SystemExit('Stop all runner processes owned by this user before reinstalling')
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
# Existing account lock files also detect same-user executors under other homes.
account_handles = []
lock_directory = pathlib.Path.home()/'.local/state/starslab-runner/account-locks'
if lock_directory.exists():
    if lock_directory.is_symlink() or lock_directory.stat().st_uid != os.getuid():
        raise SystemExit('Account lock directory is not owned by this user')
    for path in lock_directory.glob('*.lock'):
        fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        handle = os.fdopen(fd, 'a')
        account_handles.append(handle)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Stop the active account executor before reinstalling')
state = pathlib.Path.home()/'.local/state/starslab-runner'
state.mkdir(parents=True, exist_ok=True, mode=0o700)
if state.is_symlink() or state.stat().st_uid != os.getuid():
    raise SystemExit('Installation lock directory is not owned by this user')
state.chmod(0o700)
fd = os.open(state/'installation.lock', os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW, 0o600)
installation = os.fdopen(fd, 'a')
os.fchmod(fd, 0o600)
try:
    fcntl.flock(installation, fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit('Stop all runner CLI processes before reinstalling')
home = pathlib.Path(sys.argv[1])
handles = []
if home.exists():
    if home.is_symlink() or home.stat().st_uid != os.getuid() or home.stat().st_mode & 0o077:
        raise SystemExit('Runner home must be private and owned by the installing user')
    for mode in ('dry_run', 'live'):
        fd = os.open(home / f'htx-{mode}.sqlite.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        handle = os.fdopen(fd, 'a')
        handles.append(handle)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Stop the executor before reinstalling')
subprocess.run(['uv', 'tool', 'install', '--force', '--reinstall', '--python', '3.13',
    'https://github.com/stars-labs/quant/releases/download/runner-v0.2.1/starslab_runner-0.2.1-py3-none-any.whl'], check=True)
PYTHON

# Installation leaves existing configuration untouched, including legacy schemas.
: "Executable installation complete"
runner_bin="$(uv tool dir --bin)/starslab-runner"
"$runner_bin" --help >/dev/null
if [ ! -f "$runner_home/config.json" ]; then
  "$runner_bin" --home "$runner_home" init
fi
echo "Installed and checked: $runner_bin"
echo 'Next: starslab-runner fund, then starslab-runner run --once (simulation).'
echo 'For local live authorization and display reporting, follow the setup guide:'
echo 'https://github.com/stars-labs/quant/tree/runner-v0.2.1/runner'
