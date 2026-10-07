#!/usr/bin/env bash
set -euo pipefail
repo="${REPO:-Apeloff1/Skeleton}"; branch="${BRANCH:-main}"; required_check="Merge Readiness"; required_app_id="15368"; failures=0
[[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || { echo "error: REPO must be owner/name" >&2; exit 2; }
[[ "$branch" =~ ^[A-Za-z0-9._/-]+$ && "$branch" != *".."* && "$branch" != /* && "$branch" != */ ]] || { echo "error: BRANCH contains unsupported characters" >&2; exit 2; }
command -v gh >/dev/null 2>&1 || { echo "error: GitHub CLI (gh) is required" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "error: Python 3 is required" >&2; exit 1; }
gh auth status -h github.com >/dev/null 2>&1 || { echo "error: gh is not authenticated to github.com" >&2; exit 1; }
mark_failure(){ failures=$((failures+1)); printf 'FAIL: %s\n' "$1" >&2; }
admin="$(gh api "repos/${repo}" --jq '.permissions.admin // false')"; [[ "$admin" == true ]] && echo "PASS: active gh identity has repository admin permission" || mark_failure "active gh identity does not have repository admin permission"
protected="$(gh api "repos/${repo}/branches/${branch}" --jq '.protected // false')"
if [[ "$protected" == true ]]; then
  echo "PASS: ${branch} is protected"
  protection_json="$(mktemp)"; trap 'rm -f "$protection_json"' EXIT; gh api "repos/${repo}/branches/${branch}/protection" >"$protection_json"
  IFS=$'\t' read -r check_present enforce_admins strict pr_gate conversations force_pushes deletions < <(python3 - "$protection_json" "$required_check" "$required_app_id" <<'PY'
import json,sys
path,required,app_id_raw=sys.argv[1:]; app_id=int(app_id_raw)
with open(path,encoding="utf-8") as f: data=json.load(f)
status=data.get("required_status_checks") or {}; checks=status.get("checks") or []
values=(any(isinstance(x,dict) and x.get("context")==required and x.get("app_id")==app_id for x in checks),bool((data.get("enforce_admins") or {}).get("enabled")),bool(status.get("strict")),data.get("required_pull_request_reviews") is not None,bool((data.get("required_conversation_resolution") or {}).get("enabled")),bool((data.get("allow_force_pushes") or {}).get("enabled")),bool((data.get("allow_deletions") or {}).get("enabled")))
print("\t".join(str(x).lower() for x in values))
PY
)
  [[ "$check_present" == true ]] && echo "PASS: required check is bound to GitHub Actions" || mark_failure "required check is not bound to GitHub Actions app ${required_app_id}"
  [[ "$enforce_admins" == true ]] && echo "PASS: protection applies to administrators" || mark_failure "administrators can bypass protection"
  [[ "$strict" == true ]] && echo "PASS: required checks require an up-to-date branch" || mark_failure "strict required-status mode is disabled"
  [[ "$pr_gate" == true ]] && echo "PASS: pull-request changes are required" || mark_failure "pull-request review gate is absent"
  [[ "$conversations" == true ]] && echo "PASS: conversations must be resolved" || mark_failure "conversation resolution is not required"
  [[ "$force_pushes" == false ]] && echo "PASS: force pushes are blocked" || mark_failure "force pushes are allowed"
  [[ "$deletions" == false ]] && echo "PASS: branch deletion is blocked" || mark_failure "branch deletion is allowed"
else mark_failure "${branch} is not protected"; fi
printf '\nActions defaults\n'; defaults="$(gh api "repos/${repo}/actions/permissions/workflow" --jq '.default_workflow_permissions')"; approvals="$(gh api "repos/${repo}/actions/permissions/workflow" --jq '.can_approve_pull_request_reviews')"
[[ "$defaults" == read ]] && echo "PASS: default workflow token permission is read" || mark_failure "default workflow token permission is ${defaults}"
[[ "$approvals" == false ]] && echo "PASS: Actions cannot approve pull requests" || mark_failure "Actions can approve pull requests"
printf '\nRulesets\n'; echo "INFO: repository rulesets=$(gh api "repos/${repo}/rulesets" --jq 'length' 2>/dev/null || printf unavailable)"
printf '\nSecurity-and-analysis metadata\n'; gh api "repos/${repo}" --jq '.security_and_analysis // {}' 2>/dev/null || true
printf '\nDeployment environments (names and protection rule types only)\n'; gh api "repos/${repo}/environments" --jq '.environments[]? | [.name, ([.protection_rules[]?.type] | join(","))] | @tsv' 2>/dev/null || echo "INFO: environment metadata unavailable"
(( failures == 0 )) || { echo "Owner security audit: ${failures} required control(s) missing" >&2; exit 1; }; echo "Owner security audit: required repository controls pass"
