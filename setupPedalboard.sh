#!/usr/bin/env bash
set -euo pipefail

skipSystem="false"
devInstall="false"
pythonCommand=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-system) skipSystem="true"; shift ;;
    --dev) devInstall="true"; shift ;;
    --python-exe) pythonCommand="${2:?--python-exe requires a path}"; shift 2 ;;
    *)
      printf 'Usage: %s [--skip-system] [--dev] [--python-exe PATH]\n' "$0" >&2
      exit 2
      ;;
  esac
done

repoRoot="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venvDir="$repoRoot/python/.venv"

isSupportedPython() {
  local candidate="$1"
  [[ -x "$candidate" ]] || command -v "$candidate" >/dev/null 2>&1 || return 1
  "$candidate" -c 'import sys, venv; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 13) else 1)'
}

if [[ -n "$pythonCommand" ]]; then
  isSupportedPython "$pythonCommand" || {
    printf '%s must be Python 3.10, 3.11, or 3.12.\n' "$pythonCommand" >&2
    exit 1
  }
else
  for candidate in python3.12 python3.11 python3.10 python3; do
    if isSupportedPython "$candidate"; then
      pythonCommand="$candidate"
      break
    fi
  done
fi

[[ -n "$pythonCommand" ]] || {
  printf 'Python 3.10, 3.11, or 3.12 is required for the supported RtMidi package.\n' >&2
  exit 1
}

if [[ "$skipSystem" != "true" ]]; then
  command -v apt-get >/dev/null 2>&1 || {
    printf 'This v0.8.0 setup supports APT-based Linux Mint/Ubuntu systems; install prerequisites manually and use --skip-system.\n' >&2
    exit 1
  }
  privilege=(sudo)
  [[ "${EUID:-$(id -u)}" -eq 0 ]] && privilege=()
  printf 'Installing BlueZ, ALSA tools/runtime, and Python venv support...\n'
  "${privilege[@]}" apt-get update
  "${privilege[@]}" apt-get install -y bluez alsa-utils libasound2 python3-venv
fi

for requiredCommand in bluetoothctl gatttool aconnect; do
  command -v "$requiredCommand" >/dev/null 2>&1 || {
    printf '%s is required; install the full BlueZ and ALSA utilities packages.\n' "$requiredCommand" >&2
    exit 1
  }
done
if [[ ! -e /dev/snd/seq ]]; then
  printf 'Warning: /dev/snd/seq is unavailable; Katana MIDI will not work until the ALSA sequencer is available.\n' >&2
fi

"$pythonCommand" -m venv "$venvDir"
installExtra="katana"
[[ "$devInstall" == "true" ]] && installExtra="katana,dev"
"$venvDir/bin/python" -m pip install --editable "$repoRoot[$installExtra]"
"$venvDir/bin/python" -m blueboard_macro_handler --version
printf 'Setup complete. Connect both devices, then run ./onboardPedalboard.sh\n'
