#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python_exe="$repo_root/python/.venv/bin/python"
config_file="$repo_root/python/config/katana-pedalboard.local.json"
[[ -x "$python_exe" ]] || { printf 'Run ./setupPedalboard.sh first.\n' >&2; exit 1; }
[[ -f "$config_file" ]] || { printf 'Run ./configurePedalboard.sh first.\n' >&2; exit 1; }
exec "$python_exe" -m blueboard_macro_handler probe-effects --config "$config_file" "$@"
