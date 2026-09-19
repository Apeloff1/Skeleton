#!/usr/bin/env bash
set -euo pipefail

# Owner-side escape hatch for a clogged GitHub Actions queue.
#
# This mirrors the safety policy in .github/workflows/queue-drain.yml but runs
# through the repository owner's local `gh` authentication, so the cleanup does
# not have to wait for the queued drainer workflow to receive a runner.

repo="${REPO:-Apeloff1/Skeleton}"
mode="${1:---dry-run}"
max_cancel="${MAX_CANCEL:-500}"

if [[ ! "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "error: REPO must be a safe owner/name value" >&2
  exit 2
fi
if [[ ! "$max_cancel" =~ ^[0-9]+$ || "$max_cancel" -lt 1 ]]; then
  echo "error: MAX_CANCEL must be a positive integer" >&2
  exit 2
fi
case "$mode" in
  --dry-run|--apply|apply) ;;
  *)
    echo "usage: REPO=owner/name MAX_CANCEL=500 $0 [--dry-run|--apply]" >&2
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

token="$(gh auth token)"
if [[ -z "$token" ]]; then
  echo "error: gh did not return an authentication token" >&2
  exit 1
fi
trap 'unset token GH_TOKEN' EXIT
export GH_TOKEN="$token"
export REPO="$repo"
export MAX_CANCEL="$max_cancel"
if [[ "$mode" == "--dry-run" ]]; then
  export DRY_RUN=1
else
  export DRY_RUN=0
fi

python3 - <<'PY'
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

repo = os.environ["REPO"]
token = os.environ["GH_TOKEN"]
dry_run = os.environ.get("DRY_RUN") == "1"
max_cancel = int(os.environ["MAX_CANCEL"])
api = "https://api.github.com"
headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {token}",
    "X-GitHub-Api-Version": "2026-03-10",
    "User-Agent": "skeleton-owner-queue-drainer",
}
retryable = frozenset({0, 429, 500, 502, 503, 504})

# Keep this set aligned with .github/workflows/queue-drain.yml. These runs are
# the recovery/control plane or canonical post-merge evidence and are never
# cancellation targets merely because main advances.
control_plane_paths = frozenset(
    {
        ".github/workflows/actions-housekeeping-cli.yml",
        ".github/workflows/branch-clean.yml",
        ".github/workflows/branch-archive.yml",
        ".github/workflows/branch-flow.yml",
        ".github/workflows/branch-repair-100.yml",
        ".github/workflows/merge-readiness.yml",
        ".github/workflows/pr-obsolete-run-drain.yml",
        ".github/workflows/queue-drain.yml",
    }
)


def request(path, *, method="GET"):
    req = urllib.request.Request(
        api + path,
        data=b"" if method != "GET" else None,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except urllib.error.URLError:
        return 0, None


def main_sha():
    status, payload = request(f"/repos/{repo}/branches/main")
    sha = ((payload or {}).get("commit") or {}).get("sha", "")
    if status != 200 or not sha:
        raise SystemExit(f"failed to resolve main HEAD: HTTP {status}")
    return sha


def list_runs(*, run_status=None, head_sha=None):
    out = []
    for page in range(1, 11):
        params = {"per_page": 100, "page": page}
        if run_status:
            params["status"] = run_status
        if head_sha:
            params["head_sha"] = head_sha
        query = urllib.parse.urlencode(params)
        status, payload = request(f"/repos/{repo}/actions/runs?{query}")
        if status != 200 or not isinstance(payload, dict):
            raise SystemExit(f"failed to list Actions runs: HTTP {status}")
        batch = payload.get("workflow_runs") or []
        out.extend(batch)
        if len(batch) < 100:
            break
    return out


def workflow_event_key(run):
    return (int(run.get("workflow_id") or 0), run.get("event") or "")


def lane_key(run):
    return (
        int(run.get("workflow_id") or 0),
        run.get("head_branch") or "",
        run.get("event") or "",
    )


def usable_replacement(run):
    return not (
        run.get("status") == "completed" and run.get("conclusion") == "cancelled"
    )


def path(run):
    return run.get("path") or ""


def is_control_plane(run):
    return path(run) in control_plane_paths


def cancel(run_id):
    status = 0
    for attempt in range(3):
        status, _ = request(
            f"/repos/{repo}/actions/runs/{run_id}/cancel", method="POST"
        )
        if status not in retryable:
            return status
        if attempt < 2:
            time.sleep(2**attempt)
    return status


attempted = set()
total_selected = 0
total_accepted = 0
total_moved = 0
total_failed = 0
passes = 1 if dry_run else 4

for pass_no in range(1, passes + 1):
    head = main_sha()
    head_runs = list_runs(head_sha=head)
    replacement_keys = {
        workflow_event_key(run) for run in head_runs if usable_replacement(run)
    }
    queued = list_runs(run_status="queued")
    active = list_runs(run_status="in_progress")

    selected = []
    seen = set()
    preserved_control = 0
    preserved_last_validation = 0

    for run in sorted(
        queued, key=lambda item: item.get("created_at") or "", reverse=True
    ):
        run_id = int(run.get("id") or 0)
        if not run_id or run_id in attempted:
            continue
        if is_control_plane(run):
            preserved_control += 1
            continue

        lane = lane_key(run)
        replacement = workflow_event_key(run)
        old_main = (
            (run.get("head_branch") or "") == "main"
            and (run.get("head_sha") or "") != head
        )

        if old_main:
            if replacement in replacement_keys:
                selected.append((run, "obsolete-main"))
                continue
            if lane in seen:
                selected.append((run, "duplicate-old-main"))
            else:
                seen.add(lane)
                preserved_last_validation += 1
            continue

        if lane in seen:
            selected.append((run, "duplicate-lane"))
        else:
            seen.add(lane)

    for run in active:
        run_id = int(run.get("id") or 0)
        if not run_id or run_id in attempted:
            continue
        if is_control_plane(run):
            preserved_control += 1
            continue
        if (
            (run.get("head_branch") or "") == "main"
            and (run.get("head_sha") or "") != head
            and path(run).startswith("dynamic/")
            and workflow_event_key(run) in replacement_keys
        ):
            selected.append((run, "stale-dynamic-active"))

    remaining = max_cancel - total_selected
    if remaining <= 0:
        print(f"cancellation cap reached: MAX_CANCEL={max_cancel}")
        break
    selected = selected[:remaining]

    print(
        f"pass={pass_no} main={head} queued={len(queued)} active={len(active)} "
        f"selected={len(selected)} control_plane_preserved={preserved_control} "
        f"last_validation_preserved={preserved_last_validation} dry_run={dry_run}"
    )

    # Apply mode is intentionally stricter than the selection pass. A new main
    # head invalidates the replacement evidence we just computed, so perform no
    # mutations from that snapshot and let the next pass reselect against the
    # live repository state.
    if not dry_run and selected:
        live_head = main_sha()
        if live_head != head:
            print(
                f"main advanced before mutation: selected_for={head} live={live_head}; "
                "deferring this pass"
            )
            if pass_no < passes:
                time.sleep(8)
            continue

    total_selected += len(selected)

    for run, reason in selected:
        run_id = int(run["id"])
        print(
            "target "
            f"id={run_id} reason={reason} workflow={run.get('name')!r} "
            f"branch={run.get('head_branch')!r} sha={run.get('head_sha')!r} "
            f"path={run.get('path')!r}"
        )
        if dry_run:
            continue

        status = cancel(run_id)
        if status in {200, 202}:
            attempted.add(run_id)
            total_accepted += 1
        elif status in {404, 409, 422}:
            attempted.add(run_id)
            total_moved += 1
        else:
            attempted.add(run_id)
            total_failed += 1
            print(f"cancel failed: id={run_id} HTTP={status}")

    if not dry_run and pass_no < passes:
        time.sleep(8)

print(
    f"summary selected={total_selected} accepted={total_accepted} "
    f"already_moved={total_moved} failed={total_failed} cap={max_cancel}"
)

if total_failed:
    raise SystemExit(f"queue drain had {total_failed} cancellation failure(s)")
PY
