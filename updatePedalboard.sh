#!/usr/bin/env bash
set -euo pipefail
branch="main"
if [[ "${1:-}" == "--branch" ]]; then
  branch="${2:?--branch requires main or dev}"
  shift 2
fi
[[ "$branch" == "main" || "$branch" == "dev" ]] || { printf 'Branch must be main or dev.\n' >&2; exit 2; }
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -z "$(git -C "$repo_root" status --porcelain)" ]] || {
  printf 'Update stopped: commit or stash local changes first.\n' >&2
  exit 1
}
git -C "$repo_root" fetch origin "$branch"
git -C "$repo_root" switch "$branch"
git -C "$repo_root" pull --ff-only origin "$branch"
exec "$repo_root/setupPedalboard.sh" "$@"
