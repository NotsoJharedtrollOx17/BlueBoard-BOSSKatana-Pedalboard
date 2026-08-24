#!/usr/bin/env bash
set -euo pipefail
skip_system="false"
dev_install="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-system) skip_system="true"; shift ;;
    --dev) dev_install="true"; shift ;;
    *) printf 'Usage: %s [--skip-system] [--dev]\n' "$0" >&2; exit 2 ;;
  esac
done
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv_dir="$repo_root/python/.venv"

python_command=""
for candidate in python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 13) else 1)'; then
    python_command="$candidate"
    break
  fi
done
[[ -n "$python_command" ]] || {
  printf 'Python 3.10, 3.11, or 3.12 is required because python-rtmidi 1.5.8 has no wheel for Python 3.13+.\n' >&2
  exit 1
}

if [[ "$skip_system" != "true" ]] && command -v apt-get >/dev/null 2>&1; then
  privilege=(sudo)
  [[ "${EUID:-$(id -u)}" -eq 0 ]] && privilege=()
  printf 'Installing BlueZ, Python venv support, and ALSA runtime libraries...\n'
  "${privilege[@]}" apt-get update
  "${privilege[@]}" apt-get install -y bluez python3-venv libasound2
fi

"$python_command" -m venv "$venv_dir"
extra="katana,linux"
[[ "$dev_install" == "true" ]] && extra="katana,linux,dev"
"$venv_dir/bin/python" -m pip install --editable "$repo_root[$extra]"
"$venv_dir/bin/python" -m blueboard_macro_handler --version
printf 'Setup complete. Connect both devices, then run ./configurePedalboard.sh\n'
