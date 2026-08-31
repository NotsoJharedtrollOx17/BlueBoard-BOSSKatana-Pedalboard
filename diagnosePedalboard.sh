#!/usr/bin/env bash
set -euo pipefail

repoRoot="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pythonExe="$repoRoot/python/.venv/bin/python"
configFile="$repoRoot/python/config/katana-pedalboard.local.json"
[[ -x "$pythonExe" ]] || { printf 'Run ./setupPedalboard.sh first.\n' >&2; exit 1; }
[[ -f "$configFile" ]] || { printf 'Run ./onboardPedalboard.sh first.\n' >&2; exit 1; }
exec "$pythonExe" -m blueboard_macro_handler doctor --config "$configFile" --scan-timeout 20 "$@"
