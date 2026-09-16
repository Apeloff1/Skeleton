#!/usr/bin/env bash
set -euo pipefail

# Owner-side bootstrap for the admin-only GitHub branch-protection control.
#
# This intentionally uses the caller's local `gh` authentication rather than
# the repository GitHub App. The app used by automation may have repository
# write/admin-like capabilities without the separate Administration: write
# permission required by the branch-protection API.

repo="${REPO:-Apeloff1/Skeleton}"
branch="${BRANCH:-main}"
required_check="Merge Readiness"
mode="${1:---verify}"

if [[ ! "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "error: REPO must be a safe owner/name value" >&2
  exit 2
fi
if [[ ! "$branch" =~ ^[A-Za-z0-9._/-]+$ || "$branch" == *".."* || "$branch" == /* || "$branch" == */ ]]; then
  echo "error: BRANCH contains unsupported characters" >&2
  exit 2
fi

case "$mode" in
  apply|--apply|--dry-run|--verify) ;;
  *)
    echo "usage: REPO=owner/name BRANCH=main $0 [--verify|--dry-run|--apply]" >&2
    exit 2
    ;;
esac

if ! command -v gh >/dev/null 2>&1; then
  echo "error: GitHub CLI (gh) is required" >&2
  exit 1
fi

if ! gh auth status -h github.com >/dev/null 2>&1; then
  echo "error: gh is not authenticated to github.com" >&2
  exit 1
fi

admin="$(gh api "repos/${repo}" --jq '.permissions.admin // false')"
if [[ "$admin" != "true" ]]; then
  echo "error: the active gh identity is not an admin/owner of ${repo}" >&2
  exit 1
fi

verify() {
  local protected check_present enforce_admins strict pr_gate conversations force_pushes deletions

  protected="$(gh api "repos/${repo}/branches/${branch}" --jq '.protected')"
  if [[ "$protected" != "true" ]]; then
    echo "NOT ENFORCED: ${repo}:${branch} is not protected" >&2
    return 1
  fi

  gh api "repos/${repo}/branches/${branch}/protection" --jq '
    {
      enforce_admins: .enforce_admins.enabled,
      required_checks: .required_status_checks.contexts,
      strict: .required_status_checks.strict,
      pull_request_reviews: (.required_pull_request_reviews != null),
      approving_reviews_required: (.required_pull_request_reviews.required_approving_review_count // null),
      conversation_resolution: .required_conversation_resolution.enabled,
      force_pushes_allowed: .allow_force_pushes.enabled,
      deletions_allowed: .allow_deletions.enabled
    }
  '

  check_present="false"
  if gh api "repos/${repo}/branches/${branch}/protection" --jq '.required_status_checks.contexts[]' | grep -Fxq "$required_check"; then
    check_present="true"
  fi
  enforce_admins="$(gh api "repos/${repo}/branches/${branch}/protection" --jq '.enforce_admins.enabled')"
  strict="$(gh api "repos/${repo}/branches/${branch}/protection" --jq '.required_status_checks.strict')"
  pr_gate="$(gh api "repos/${repo}/branches/${branch}/protection" --jq '.required_pull_request_reviews != null')"
  conversations="$(gh api "repos/${repo}/branches/${branch}/protection" --jq '.required_conversation_resolution.enabled')"
  force_pushes="$(gh api "repos/${repo}/branches/${branch}/protection" --jq '.allow_force_pushes.enabled')"
  deletions="$(gh api "repos/${repo}/branches/${branch}/protection" --jq '.allow_deletions.enabled')"

  if [[ "$check_present" != "true" || "$enforce_admins" != "true" || "$strict" != "true" || "$pr_gate" != "true" || "$conversations" != "true" || "$force_pushes" != "false" || "$deletions" != "false" ]]; then
    echo "error: protection exists but does not match the expected hardened policy" >&2
    return 1
  fi

  echo "OK: ${repo}:${branch} enforces ${required_check} for admins and pull requests"
}

if [[ "$mode" == "--verify" ]]; then
  verify
  exit $?
fi

payload='{
  "required_status_checks": {
    "strict": true,
    "contexts": ["Merge Readiness"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": true,
  "lock_branch": false,
  "allow_fork_syncing": false
}'

if [[ "$mode" == "--dry-run" ]]; then
  printf '%s\n' "$payload"
  exit 0
fi

printf '%s\n' "$payload" | gh api \
  --method PUT \
  -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2022-11-28' \
  "repos/${repo}/branches/${branch}/protection" \
  --input - >/dev/null

verify
