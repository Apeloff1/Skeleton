#!/usr/bin/env bash
set -euo pipefail

# Owner-side bootstrap for repository workflow hygiene settings that require
# repository administration permission. This uses the owner's local `gh`
# authentication rather than the routine automation app connection.

repo="${REPO:-Apeloff1/Skeleton}"
mode="${1:---verify}"

if [[ ! "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "error: REPO must be a safe owner/name value" >&2
  exit 2
fi

case "$mode" in
  --verify|--dry-run|--apply|apply) ;;
  *)
    echo "usage: REPO=owner/name $0 [--verify|--dry-run|--apply]" >&2
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
  echo "error: active gh identity is not an admin/owner of ${repo}" >&2
  exit 1
fi

verify() {
  local allow_update delete_on_merge auto_merge signoff
  allow_update="$(gh api "repos/${repo}" --jq '.allow_update_branch // false')"
  delete_on_merge="$(gh api "repos/${repo}" --jq '.delete_branch_on_merge // false')"
  auto_merge="$(gh api "repos/${repo}" --jq '.allow_auto_merge // false')"
  signoff="$(gh api "repos/${repo}" --jq '.web_commit_signoff_required // false')"

  printf 'allow_update_branch=%s\n' "$allow_update"
  printf 'delete_branch_on_merge=%s\n' "$delete_on_merge"
  printf 'allow_auto_merge=%s\n' "$auto_merge"
  printf 'web_commit_signoff_required=%s\n' "$signoff"

  local failed=0
  if [[ "$allow_update" != "true" ]]; then
    echo "error: update-branch support is disabled" >&2
    failed=1
  fi
  if [[ "$delete_on_merge" != "true" ]]; then
    echo "error: merged head branches are not deleted automatically" >&2
    failed=1
  fi
  if [[ "$auto_merge" != "true" ]]; then
    echo "error: repository auto-merge support is disabled" >&2
    failed=1
  fi
  if [[ "$signoff" != "true" ]]; then
    echo "error: web commit signoff is not required" >&2
    failed=1
  fi

  if (( failed != 0 )); then
    return 1
  fi

  echo "OK: repository workflow hygiene settings match the expected owner policy"
}

if [[ "$mode" == "--verify" ]]; then
  verify
  exit $?
fi

if [[ "$mode" == "--dry-run" ]]; then
  cat <<'EOF'
PATCH /repos/{owner}/{repo}
{
  "allow_update_branch": true,
  "delete_branch_on_merge": true,
  "allow_auto_merge": true,
  "web_commit_signoff_required": true
}
EOF
  exit 0
fi

gh api \
  --method PATCH \
  -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2022-11-28' \
  "repos/${repo}" \
  -F allow_update_branch=true \
  -F delete_branch_on_merge=true \
  -F allow_auto_merge=true \
  -F web_commit_signoff_required=true \
  >/dev/null

verify
