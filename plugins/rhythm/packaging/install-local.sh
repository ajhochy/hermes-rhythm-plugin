#!/usr/bin/env bash
# Explicit operator action. Never invoked by the build.
set -euo pipefail
rhythm_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
rhythm_package="${1:-$rhythm_repo/dist/rhythm-feature-pack}"
if [[ $# -gt 1 ]]; then
  echo "Usage: $0 [built-package-directory]" >&2
  exit 2
fi
rhythm_python=""
for candidate in "$rhythm_repo/.venv/bin/python" "$rhythm_repo/venv/bin/python" "$HOME/.hermes/hermes-agent/venv/bin/python"; do
  if [[ -x "$candidate" ]] && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
    rhythm_python="$candidate"
    break
  fi
done
if [[ -z "$rhythm_python" ]]; then
  echo "Python 3.11+ Hermes venv required; no dependencies will be installed." >&2
  exit 1
fi
PYTHONPATH="$rhythm_repo${PYTHONPATH:+:$PYTHONPATH}" "$rhythm_python" -m plugins.rhythm.packaging.install_local \
  --package "$rhythm_package" --home "$HOME/.hermes"
