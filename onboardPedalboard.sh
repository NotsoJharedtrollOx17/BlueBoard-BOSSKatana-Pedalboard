#!/usr/bin/env bash
set -euo pipefail

repoRoot="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venvPython="$repoRoot/python/.venv/bin/python"
configFile="$repoRoot/python/config/katana-pedalboard.local.json"
requiredVersion="0.8.0"
refreshEnvironment="false"
verifyExisting="false"
forceProfile="false"
devInstall="false"
skipSystem="false"
pythonCommand=""
profileOptions="false"
onboardArgs=(onboard --config "$configFile")

while [[ $# -gt 0 ]]; do
  case "$1" in
    --refresh-environment) refreshEnvironment="true"; shift ;;
    --verify-existing) verifyExisting="true"; shift ;;
    --force) forceProfile="true"; onboardArgs+=(--force); shift ;;
    --dev) devInstall="true"; shift ;;
    --skip-system) skipSystem="true"; shift ;;
    --python-exe) pythonCommand="${2:?--python-exe requires a path}"; shift 2 ;;
    --input|--output|--model|--layout|--midi-channel|--firmware|--name|--address|--scan-timeout)
      option="$1"; value="${2:?$1 requires a value}"; onboardArgs+=("$option" "$value"); profileOptions="true"; shift 2 ;;
    --non-interactive|--accept-profile-state-defaults)
      onboardArgs+=("$1"); profileOptions="true"; shift ;;
    --log-file) onboardArgs+=("$1" "${2:?--log-file requires a path}"); shift 2 ;;
    --debug|--json-logs) onboardArgs+=("$1"); shift ;;
    *)
      printf 'Usage: %s [setup options] [--verify-existing|--force] [onboarding options]\n' "$0" >&2
      exit 2
      ;;
  esac
done

environmentReady() {
  [[ -x "$venvPython" ]] || return 1
  [[ "$($venvPython -c "import sys; import blueboard_macro_handler as package; print(int((3, 10) <= sys.version_info[:2] < (3, 13) and package.__version__ == '$requiredVersion'))" 2>/dev/null)" == "1" ]]
}

if [[ "$refreshEnvironment" == "true" ]] || ! environmentReady; then
  setupArgs=()
  [[ "$devInstall" == "true" ]] && setupArgs+=(--dev)
  [[ "$skipSystem" == "true" ]] && setupArgs+=(--skip-system)
  [[ -n "$pythonCommand" ]] && setupArgs+=(--python-exe "$pythonCommand")
  printf 'Preparing the local pedalboard environment...\n'
  "$repoRoot/setupPedalboard.sh" "${setupArgs[@]}"
  environmentReady || {
    printf 'Setup completed, but the local v0.8.0 environment is not ready.\n' >&2
    exit 1
  }
else
  printf 'Reusing the compatible local v0.8.0 environment.\n'
fi

if [[ "$verifyExisting" == "true" && "$forceProfile" == "true" ]]; then
  printf '%s\n' '--verify-existing cannot be combined with --force.' >&2
  exit 2
fi
if [[ "$verifyExisting" == "true" && ! -f "$configFile" ]]; then
  printf 'No saved profile exists at %s. Remove --verify-existing to create one.\n' "$configFile" >&2
  exit 1
fi
if [[ -f "$configFile" && "$forceProfile" != "true" && "$profileOptions" == "true" && "$verifyExisting" != "true" ]]; then
  printf 'A saved profile already exists. Use --verify-existing or add --force to replace it.\n' >&2
  exit 2
fi
if [[ "$verifyExisting" == "true" || ( -f "$configFile" && "$forceProfile" != "true" ) ]]; then
  onboardArgs+=(--verify-existing)
  printf 'Checking the saved pedalboard profile with fresh hardware discovery...\n'
else
  printf 'Starting unified read-only Linux hardware onboarding...\n'
fi

exec "$venvPython" -m blueboard_macro_handler "${onboardArgs[@]}"
