"""Cancel GitHub Actions runs that have remained queued for more than three hours.

Only the exact "queued" state is eligible. Re-fetch each candidate immediately
before requesting ordinary cancellation; never force-cancel active jobs, alter
required-check rules, or count a requested cancellation as a terminal result.
Runs stuck in GitHub's provider-side HTTP 409 state remain visible failures.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

MAX_AGE_SECONDS = 3 * 60 * 60
MAX_PAGES = 10
MAX_CANCEL_REQUESTS = 80
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
API_VERSION = "2022-11-28"


class CleanupError(RuntimeError):
    """Fail closed when the API inventory cannot be trusted."""


def created_at_seconds(value: object) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CleanupError("GitHub run created_at is missing or malformed")
    try:
        timestamp = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CleanupError("invalid run creation timestamp") from exc
    if timestamp.tzinfo is None:
        raise CleanupError("run creation timestamp lacks timezone")
    return int(timestamp.timestamp())


def stale_queued(run: dict[str, Any], *, now: int, current: int) -> bool:
    identifier = run.get("id")
    if type(identifier) is not int or identifier <= 0:
        raise CleanupError("invalid GitHub run identity")
    if identifier == current or run.get("status") != "queued":
        return False
    age = now - created_at_seconds(run.get("created_at"))
    if age < 0:
        raise CleanupError("future-dated GitHub run")
    return age > MAX_AGE_SECONDS


@dataclass
class GitHubActions:
    repository: str
    token: str
    api: str = "https://api.github.com"

    def request(self, path: str, *, method: str = "GET") -> tuple[int, Any]:
        request = urllib.request.Request(
            self.api.rstrip("/") + path,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "skeleton-stale-queue-expiry",
            },
            data=b"" if method == "POST" else None,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read()
                return response.status, json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            return exc.code, None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise CleanupError("GitHub Actions API transport failed") from exc

    def checked_get(self, path: str) -> Any:
        status, body = self.request(path)
        if status != 200:
            raise CleanupError(f"GitHub Actions API read failed: HTTP {status}")
        return body

    def queued_runs(self) -> list[dict[str, Any]]:
        found: dict[int, dict[str, Any]] = {}
        for page in range(1, MAX_PAGES + 1):
            query = urllib.parse.urlencode(
                {"status": "queued", "per_page": 100, "page": page}
            )
            payload = self.checked_get(
                f"/repos/{self.repository}/actions/runs?{query}"
            )
            if not isinstance(payload, dict) or not isinstance(
                payload.get("workflow_runs"), list
            ):
                raise CleanupError("invalid queued Actions listing")
            rows = payload["workflow_runs"]
            for row in rows:
                if not isinstance(row, dict) or type(row.get("id")) is not int:
                    raise CleanupError("invalid queued Actions inventory row")
                found[row["id"]] = row
            if len(rows) < 100:
                return list(found.values())
        raise CleanupError("queued run inventory exceeds bounded page limit")

    def unchanged_and_queued(self, row: dict[str, Any], *, now: int, current: int) -> bool:
        run_id = row["id"]
        detail = self.checked_get(f"/repos/{self.repository}/actions/runs/{run_id}")
        if not isinstance(detail, dict) or detail.get("id") != run_id:
            raise CleanupError("run identity changed during preflight")
        if detail.get("created_at") != row.get("created_at"):
            raise CleanupError("run creation timestamp changed during preflight")
        if not stale_queued(detail, now=now, current=current):
            return False
        jobs = self.checked_get(
            f"/repos/{self.repository}/actions/runs/{run_id}/jobs?per_page=100"
        )
        if not isinstance(jobs, dict) or not isinstance(jobs.get("jobs"), list):
            raise CleanupError("missing job-level cancellation evidence")
        if type(jobs.get("total_count")) is not int or jobs["total_count"] > 100:
            raise CleanupError("job inventory was incomplete")
        return not any(
            job.get("status") == "in_progress"
            for job in jobs["jobs"] if isinstance(job, dict)
        )

    def cancel(self, run_id: int) -> int:
        code, _ = self.request(
            f"/repos/{self.repository}/actions/runs/{run_id}/cancel",
            method="POST",
        )
        return code


def cleanup(client: GitHubActions, *, now: int, current: int,
            dry_run: bool = False) -> dict[str, int]:
    rows = client.queued_runs()
    stale = [run for run in rows if stale_queued(run, now=now, current=current)]
    stale.sort(key=lambda row: (row["created_at"], row["id"]))
    counters = {
        "queued_seen": len(rows), "older_than_three_hours": len(stale),
        "considered": 0, "cancel_requested": 0, "confirmed_cancelled": 0,
        "already_moved": 0, "provider_conflict": 0, "failed": 0,
        "deferred": max(0, len(stale) - MAX_CANCEL_REQUESTS),
    }
    for row in stale[:MAX_CANCEL_REQUESTS]:
        ident = row["id"]
        if not client.unchanged_and_queued(row, now=int(time.time()), current=current):
            counters["already_moved"] += 1
            continue
        counters["considered"] += 1
        if dry_run:
            print(f"dry-run: queued stale run={ident} created={row['created_at']}")
            continue
        status = client.cancel(ident)
        if status in (200, 202):
            counters["cancel_requested"] += 1
            confirmed = client.checked_get(
                f"/repos/{client.repository}/actions/runs/{ident}"
            )
            if (isinstance(confirmed, dict) and confirmed.get("status") == "completed"
                    and confirmed.get("conclusion") == "cancelled"):
                counters["confirmed_cancelled"] += 1
            print(f"cancellation requested: run={ident} http={status}")
        elif status in (409, 422):
            counters["provider_conflict"] += 1
            print(f"provider refused queued cancellation: run={ident} http={status}")
        elif status == 404:
            counters["already_moved"] += 1
        else:
            counters["failed"] += 1
            print(f"cancellation not accepted: run={ident} http={status}")
            if status in (403, 429):
                counters["deferred"] += sum(
                    1 for item in stale[:MAX_CANCEL_REQUESTS]
                    if (item["created_at"], item["id"]) >
                    (row["created_at"], row["id"])
                )
                break
    return counters


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    ref = os.environ.get("GITHUB_REF", "")
    current_str = os.environ.get("GITHUB_RUN_ID", "")
    if (not REPOSITORY_PATTERN.fullmatch(repository) or not token
            or ref != "refs/heads/main" or not current_str.isdecimal()):
        raise CleanupError("cleanup requires authenticated main-branch GitHub Actions")
    client = GitHubActions(
        repository, token, os.environ.get("GITHUB_API_URL", "https://api.github.com")
    )
    result = cleanup(client, now=int(time.time()), current=int(current_str),
                     dry_run=args.dry_run)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        lines = ["## Three-hour queued Actions expiry", "",
                 f"- Dry run: {args.dry_run}",
                 f"- Expiry threshold: strictly older than {MAX_AGE_SECONDS} seconds"]
        lines.extend(f"- {k}: {v}" for k, v in result.items())
        Path(summary).open("a", encoding="utf-8").write("\n".join(lines) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
