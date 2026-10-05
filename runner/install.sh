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

if command -v systemctl >/dev/null 2>&1 && systemctl --user is-active --quiet starslab-runner.service; then
  echo 'Stop your runner with systemctl --user stop starslab-runner before upgrading.' >&2
  exit 1
fi

uv tool install --force --reinstall --python 3.13 \
  'https://github.com/stars-labs/quant/releases/download/runner-v0.1.0/starslab_runner-0.1.0-py3-none-any.whl'
runner_bin="$(uv tool dir --bin)/starslab-runner"
"$runner_bin" --help >/dev/null
"$runner_bin" init
echo "Installed and checked: $runner_bin"
echo 'Next: starslab-runner fund, then starslab-runner run --once (simulation).'
echo 'For local live authorization and display reporting, follow the setup guide:'
echo 'https://github.com/stars-labs/quant/tree/runner-v0.1.0/runner'
