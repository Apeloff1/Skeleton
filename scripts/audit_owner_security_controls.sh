#!/usr/bin/env bash
set -euo pipefail

# Read-only audit of GitHub-side controls that repository source cannot enforce.
# Never reads or prints secret values. It reports protection/permission metadata
# only and exits non-zero when a required owner control is missing.

repo="${REPO:-Apeloff1/Skeleton}"
branch="${BRANCH:-main}"
required_check="${REQUIRED_CHECK:-Merge Readiness}"
failures=0

if [[ ! "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "error: REPO must be a safe owner/name value" >&2
  exit 2
fi
if [[ ! "$branch" =~ ^[A-Za-z0-9._/-]+$ || "$branch" == *".."* || "$branch" == /* || "$branch" == */ ]]; then
  echo "error: BRANCH contains unsupported characters" >&2
  exit 2
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "error: GitHub CLI (gh) is required" >&2
  exit 1
fi
if ! gh auth status -h github.com >/dev/null 2>&1; then
  echo "error: gh is not authenticated to github.com" >&2
  exit 1
fi

mark_failure() {
  failures=$((failures + 1))
  printf 'FAIL: %s\n' "$1" >&2
}

printf 'Repository: %s\nBranch: %s\nRequired check: %s\n\n' "$repo" "$branch" "$required_check"

admin="$(gh api "repos/${repo}" --jq '.permissions.admin // false')"
if [[ "$admin" == "true" ]]; then
  echo "PASS: active gh identity has repository admin permission"
else
  mark_failure "active gh identity does not have repository admin permission"
fi

protected="$(gh api "repos/${repo}/branches/${branch}" --jq '.protected // false')"
if [[ "$protected" == "true" ]]; then
  echo "PASS: ${branch} is protected"

  protection_json="$(mktemp)"
  trap 'rm -f "$protection_json"' EXIT
  gh api "repos/${repo}/branches/${branch}/protection" >"$protection_json"

  readarray -t protection < <(python3 - "$protection_json" "$required_check" <<'PY'
import json
import sys

path, required = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    data = json.load(handle)
checks = (data.get("required_status_checks") or {}).get("contexts") or []
print(str(required in checks).lower())
print(str(bool((data.get("enforce_admins") or {}).get("enabled"))).lower())
print(str(bool((data.get("required_status_checks") or {}).get("strict"))).lower())
print(str(data.get("required_pull_request_reviews") is not None).lower())
print(str(bool((data.get("required_conversation_resolution") or {}).get("enabled"))).lower())
print(str(bool((data.get("allow_force_pushes") or {}).get("enabled"))).lower())
print(str(bool((data.get("allow_deletions") or {}).get("enabled"))).lower())
PY
  )

  [[ "${protection[0]:-false}" == "true" ]] && echo "PASS: required check is configured" || mark_failure "required check '${required_check}' is missing"
  [[ "${protection[1]:-false}" == "true" ]] && echo "PASS: protection applies to administrators" || mark_failure "administrators can bypass protection"
  [[ "${protection[2]:-false}" == "true" ]] && echo "PASS: required checks require an up-to-date branch" || mark_failure "strict required-status mode is disabled"
  [[ "${protection[3]:-false}" == "true" ]] && echo "PASS: pull-request changes are required" || mark_failure "pull-request review gate is absent"
  [[ "${protection[4]:-false}" == "true" ]] && echo "PASS: conversations must be resolved" || mark_failure "conversation resolution is not required"
  [[ "${protection[5]:-true}" == "false" ]] && echo "PASS: force pushes are blocked" || mark_failure "force pushes are allowed"
  [[ "${protection[6]:-true}" == "false" ]] && echo "PASS: branch deletion is blocked" || mark_failure "branch deletion is allowed"
else
  mark_failure "${branch} is not protected"
fi

printf '\nActions defaults\n'
default_workflow_permissions="$(gh api "repos/${repo}/actions/permissions/workflow" --jq '.default_workflow_permissions')"
actions_can_approve="$(gh api "repos/${repo}/actions/permissions/workflow" --jq '.can_approve_pull_request_reviews')"
[[ "$default_workflow_permissions" == "read" ]] && echo "PASS: default workflow token permission is read" || mark_failure "default workflow token permission is ${default_workflow_permissions}"
[[ "$actions_can_approve" == "false" ]] && echo "PASS: Actions cannot approve pull requests" || mark_failure "Actions can approve pull requests"

printf '\nRulesets\n'
ruleset_count="$(gh api "repos/${repo}/rulesets" --jq 'length' 2>/dev/null || printf 'unavailable')"
echo "INFO: repository rulesets=${ruleset_count}; branch protection is accepted as the canonical enforcement path"

printf '\nSecurity-and-analysis metadata\n'
security_json="$(gh api "repos/${repo}" --jq '.security_and_analysis // {}' 2>/dev/null || printf '{}')"
if [[ "$security_json" == "{}" ]]; then
  echo "INFO: security_and_analysis metadata is unavailable for this repository/account combination"
else
  printf '%s\n' "$security_json"
fi

printf '\nDeployment environments (names and protection rule types only)\n'
if environment_rows="$(gh api "repos/${repo}/environments" --jq '.environments[]? | [.name, ([.protection_rules[]?.type] | join(","))] | @tsv' 2>/dev/null)"; then
  if [[ -n "$environment_rows" ]]; then
    printf '%s\n' "$environment_rows"
  else
    echo "INFO: no repository environments are configured"
  fi
else
  echo "INFO: environment metadata is unavailable to the active gh identity"
fi

printf '\n'
if (( failures > 0 )); then
  echo "Owner security audit: ${failures} required control(s) missing" >&2
  exit 1
fi

echo "Owner security audit: required repository controls pass"
