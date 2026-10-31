#!/usr/bin/env python3
"""Delete only the next ten frozen historical Actions records via owner GitHub CLI.

Workstation usage:
  python scripts/owner_historical_actions_local_delete.py --dry-run
  python scripts/owner_historical_actions_local_delete.py --apply

No Actions runner needed. Existing canonical double-checks, immutable identities,
closed-PR/old-main proof, empty job/artifact/deployment checks remain mandatory.
"""
import argparse
import json
import os
from pathlib import Path
import runpy
import subprocess

REPO = "Apeloff1/Skeleton"
TARGETS = (
    37539069791, 37642345734, 37642355681, 37642358530,
    37642383890, 37642388873, 37642398158, 37642398159,
    37642398161, 37655496094,
)


def cli(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") == "true":
        raise SystemExit("This owner-side workaround must not run in GitHub Actions")
    root = Path(__file__).resolve().parent.parent
    if cli("git", "-C", str(root), "symbolic-ref", "--short", "HEAD") != "main":
        raise SystemExit("Checkout main before running owner-side deletion")
    local_head = cli("git", "-C", str(root), "rev-parse", "HEAD")
    live_head = json.loads(cli("gh", "api", f"repos/{REPO}/branches/main"))["commit"]["sha"]
    if local_head != live_head:
        raise SystemExit("Local checkout is not the exact current main commit")
    paths = ["scripts/owner_historical_actions_local_delete.py",
             "scripts/owner_historical_actions_cleanup.py"]
    for path in paths:
        cli("git", "-C", str(root), "ls-files", "--error-unmatch", path)
    if cli("git", "-C", str(root), "status", "--porcelain", "--", *paths):
        raise SystemExit("Cleanup code locally modified; refusing deletion")
    actor = json.loads(cli("gh", "api", "user"))
    repo = json.loads(cli("gh", "api", f"repos/{REPO}"))
    if actor.get("login") != "Apeloff1" or repo.get("full_name") != REPO or repo.get("permissions", {}).get("admin") is not True:
        raise SystemExit("Authenticated repository owner with admin access required")
    token = cli("gh", "auth", "token")
    if not token:
        raise SystemExit("GitHub CLI is not authenticated")
    os.environ.update({"GH_TOKEN": token, "GITHUB_REPOSITORY": REPO,
                       "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch"})
    core = runpy.run_path(str(root / "scripts/owner_historical_actions_cleanup.py"),
                          run_name="_historical_owner_safety_library")
    if core["canary_proved"]() is not True:
        raise SystemExit("Verified successful canary and first-run deletion required")
    manifest = {row["id"]: row for row in core["MANIFEST"]}
    if len(manifest) != 30 or any(run_id not in manifest for run_id in TARGETS):
        raise SystemExit("Frozen owner manifest mismatch")
    confirmed, skipped, refused = [], [], []
    for run_id in TARGETS:
        row = manifest[run_id]
        if not core["validate"](row) or not core["validate"](row):
            skipped.append(run_id)
            continue
        if json.loads(cli("gh", "api", f"repos/{REPO}/branches/main"))["commit"]["sha"] != local_head:
            raise SystemExit("Main advanced during validation; no further mutation")
        if args.dry_run:
            print(f"dry-run verified (not deleted): {run_id}")
            continue
        status, detail = core["request"]("DELETE", f"/actions/runs/{run_id}")
        if status in (403, 409, 422):
            if any(term in str(detail).lower() for term in ("rate limit", "abuse", "too many requests")):
                raise SystemExit(f"Provider rate limitation, stop at {run_id}: HTTP {status}")
            refused.append(run_id)
            print(f"Provider refused {run_id}: HTTP {status}; preserving")
            continue
        if status != 204:
            raise SystemExit(f"Untrusted delete result for {run_id}: HTTP {status}")
        check, _ = core["request"]("GET", f"/actions/runs/{run_id}")
        if check != 404:
            raise SystemExit(f"Delete unconfirmed for {run_id}: HTTP {check}")
        confirmed.append(run_id)
        print(f"Deleted and verified (204/404): {run_id}")
    print(json.dumps({"mode": "apply" if args.apply else "dry-run",
                      "confirmed_deleted": confirmed, "already_absent_or_protected": skipped,
                      "provider_refused": refused}, sort_keys=True))
    if refused:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
