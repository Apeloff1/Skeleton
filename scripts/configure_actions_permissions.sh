#!/usr/bin/env bash
set -euo pipefail

# Owner-side bootstrap for GitHub Actions repository defaults.
repo="${REPO:-Apeloff1/Skeleton}"
mode="${1:---verify}"

if [[ ! "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "error: REPO must be owner/name" >&2
  exit 2
fi
case "$mode" in --apply|--verify|--dry-run) ;; *) echo "usage: REPO=owner/name $0 [--verify|--dry-run|--apply]" >&2; exit 2 ;; esac
command -v gh >/dev/null 2>&1 || { echo "error: GitHub CLI (gh) is required" >&2; exit 1; }
gh auth status -h github.com >/dev/null 2>&1 || { echo "error: gh is not authenticated to github.com" >&2; exit 1; }
admin="$(gh api "repos/${repo}" --jq '.permissions.admin // false')"
[[ "$admin" == "true" ]] || { echo "error: active gh identity is not an admin/owner of ${repo}" >&2; exit 1; }
verify() {
  local defaults approvals
  defaults="$(gh api "repos/${repo}/actions/permissions/workflow" --jq '.default_workflow_permissions')"
  approvals="$(gh api "repos/${repo}/actions/permissions/workflow" --jq '.can_approve_pull_request_reviews')"
  printf 'default_workflow_permissions=%s\ncan_approve_pull_request_reviews=%s\n' "$defaults" "$approvals"
  [[ "$defaults" == "read" ]] || { echo "error: Actions default workflow permission is not read-only" >&2; return 1; }
  [[ "$approvals" == "false" ]] || { echo "error: Actions is allowed to approve pull requests" >&2; return 1; }
  echo "OK: ${repo} uses read-only Actions defaults and Actions cannot approve PRs"
}
if [[ "$mode" == "--verify" ]]; then verify; exit $?; fi
if [[ "$mode" == "--dry-run" ]]; then
  printf '%s\n' 'PUT /repos/{owner}/{repo}/actions/permissions/workflow' '{"default_workflow_permissions":"read","can_approve_pull_request_reviews":false}'
  exit 0
fi
gh api --method PUT -H 'Accept: application/vnd.github+json' -H 'X-GitHub-Api-Version: 2026-03-10' "repos/${repo}/actions/permissions/workflow" -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false >/dev/null
verify
