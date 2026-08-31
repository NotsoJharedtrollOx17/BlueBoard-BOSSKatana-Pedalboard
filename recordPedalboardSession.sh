#!/usr/bin/env bash
set -euo pipefail

repoRoot="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pythonExe="$repoRoot/python/.venv/bin/python"
configFile="$repoRoot/python/config/katana-pedalboard.local.json"
active="false"
durationMinutes=""
logDirectory="$repoRoot/logs/pedalboard-sessions"
sessionArgs=(run --config "$configFile" --json-logs)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --active) active="true"; shift ;;
    --duration-minutes) durationMinutes="${2:?--duration-minutes requires a value}"; shift 2 ;;
    --log-directory) logDirectory="${2:?--log-directory requires a path}"; shift 2 ;;
    --debug|--led-feedback) sessionArgs+=("$1"); shift ;;
    --name|--address|--scan-timeout) sessionArgs+=("$1" "${2:?$1 requires a value}"); shift 2 ;;
    *)
      printf 'Usage: %s [--active] [--duration-minutes N] [--log-directory PATH] [--debug] [--led-feedback] [device options]\n' "$0" >&2
      exit 2
      ;;
  esac
done

[[ -x "$pythonExe" ]] || { printf 'Run ./setupPedalboard.sh first.\n' >&2; exit 1; }
[[ -f "$configFile" ]] || { printf 'Run ./onboardPedalboard.sh first.\n' >&2; exit 1; }
[[ "$active" == "true" ]] && sessionArgs+=(--execute-actions)
if [[ -n "$durationMinutes" ]]; then
  durationSeconds="$($pythonExe -c 'import sys; value=float(sys.argv[1]); assert value > 0; print(value * 60)' "$durationMinutes")" || {
    printf '%s\n' '--duration-minutes must be positive.' >&2
    exit 2
  }
  sessionArgs+=(--duration-seconds "$durationSeconds")
fi

mkdir -p "$logDirectory"
timestamp="$(date +%Y%m%d-%H%M%S)"
logFile="$logDirectory/pedalboard-session-$timestamp.jsonl"
sessionArgs+=(--log-file "$logFile")

if [[ "$active" == "true" ]]; then
  printf 'Recording ACTIVE session: configured Katana actions are enabled.\n'
else
  printf 'Recording DRY-RUN session: no Katana actions will be sent.\n'
fi
printf 'Structured log: %s\n' "$logFile"
sessionPid=""
forwardSignal() {
  local signalName="$1"
  [[ -n "$sessionPid" ]] && kill -s "$signalName" "$sessionPid" 2>/dev/null || true
}
trap 'forwardSignal INT' INT
trap 'forwardSignal TERM' TERM
set +e
"$pythonExe" -m blueboard_macro_handler "${sessionArgs[@]}" &
sessionPid=$!
wait "$sessionPid"
exitStatus=$?
while kill -0 "$sessionPid" 2>/dev/null; do
  wait "$sessionPid"
  exitStatus=$?
done
set -e
trap - INT TERM
printf 'Session log retained at: %s\n' "$logFile"
exit "$exitStatus"
