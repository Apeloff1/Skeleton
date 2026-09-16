#!/usr/bin/env bash
set -euo pipefail

# Read-only audit of GitHub-side controls that repository source cannot enforce.
# Never reads or prints secret values. It reports protection/permission metadata
# only and exits non-zero when a required owner control is missing.

repo="${REPO:-Apeloff1/Skeleton}"
branch="${BRANCH:-main}"
required_check="Merge Readiness"
required_app_id="15368" # GitHub Actions
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
if ! command -v python3 >/dev/null 2>&1; then
  echo "error: Python 3 is required" >&2
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

printf 'Repository: %s\nBranch: %s\nRequired check: %s\nRequired app id: %s (GitHub Actions)\n\n' \
  "$repo" "$branch" "$required_check" "$required_app_id"

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

  IFS=$'\t' read -r check_present enforce_admins strict pr_gate conversations force_pushes deletions < <(
    python3 - "$protection_json" "$required_check" "$required_app_id" <<'PY'
import json
import sys

path, required, app_id_raw = sys.argv[1:]
app_id = int(app_id_raw)
with open(path, encoding="utf-8") as handle:
    data = json.load(handle)
status = data.get("required_status_checks") or {}
checks = status.get("checks") or []
check_present = any(
    isinstance(item, dict)
    and item.get("context") == required
    and item.get("app_id") == app_id
    for item in checks
)
values = (
    check_present,
    bool((data.get("enforce_admins") or {}).get("enabled")),
    bool(status.get("strict")),
    data.get("required_pull_request_reviews") is not None,
    bool((data.get("required_conversation_resolution") or {}).get("enabled")),
    bool((data.get("allow_force_pushes") or {}).get("enabled")),
    bool((data.get("allow_deletions") or {}).get("enabled")),
)
print("\t".join(str(value).lower() for value in values))
PY
  )

  [[ "${check_present:-false}" == "true" ]] && echo "PASS: required check is bound to GitHub Actions" || mark_failure "required check '${required_check}' is not bound to GitHub Actions app ${required_app_id}"
  [[ "${enforce_admins:-false}" == "true" ]] && echo "PASS: protection applies to administrators" || mark_failure "administrators can bypass protection"
  [[ "${strict:-false}" == "true" ]] && echo "PASS: required checks require an up-to-date branch" || mark_failure "strict required-status mode is disabled"
  [[ "${pr_gate:-false}" == "true" ]] && echo "PASS: pull-request changes are required" || mark_failure "pull-request review gate is absent"
  [[ "${conversations:-false}" == "true" ]] && echo "PASS: conversations must be resolved" || mark_failure "conversation resolution is not required"
  [[ "${force_pushes:-true}" == "false" ]] && echo "PASS: force pushes are blocked" || mark_failure "force pushes are allowed"
  [[ "${deletions:-true}" == "false" ]] && echo "PASS: branch deletion is blocked" || mark_failure "branch deletion is allowed"
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
