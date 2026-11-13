"""Owner-authorized recovery for immutable, jobless GitHub Actions tombstones.

The original canary may be queued behind the same congestion it is intended to
fix. This standalone owner job revalidates the first archived tombstone itself,
deletes it only after two complete immutable checks, and requires a verified GET
404 before working on the other 30. Every further run also gets two independent
live safety checks. Source-of-truth is GitHub, not the aged queue listing.
"""
from __future__ import annotations

import datetime
import json
import os
import time
import urllib.error
import urllib.request

REPO = "Apeloff1/Skeleton"
CANARY_RUN = 40625466138
CANARY_SHA = "5e9a6eaf214e13188e262f4e271209b7e4f5e026"
FIRST_TOMBSTONE = 34952509012
# Authoritative pre-deletion canary identity. This does not authorize any
# other run; the remaining entries are frozen separately in MANIFEST.
FIRST_ROW = {
    "id": 34952509012,
    "head_sha": "c29683c96673ef5ef6fff775a5fd9053e1bbf795",
    "created_at": "2026-09-15T09:26:44Z",
    "head_branch": "frontier/work-live12",
    "event": "pull_request",
    "path": ".github/workflows/ci.yml",
    "name": "CI/CD",
}
API_ROOT = "https://api.github.com/repos/" + REPO
LIMIT_SECONDS = 500
MAX_DELETES = 30
# Frozen, owner-authorized original inventory, obtained before destructive work.
MANIFEST = [{"id":34952509059,"head_sha":"c29683c96673ef5ef6fff775a5fd9053e1bbf795","created_at":"2026-09-15T09:26:44Z","head_branch":"frontier/work-live12","event":"pull_request","path":".github/workflows/backend-quality.yml","name":"Backend Quality"},{"id":34952509095,"head_sha":"c29683c96673ef5ef6fff775a5fd9053e1bbf795","created_at":"2026-09-15T09:26:44Z","head_branch":"frontier/work-live12","event":"pull_request","path":".github/workflows/frontier-contracts.yml","name":"Frontier Contracts"},{"id":34952518480,"head_sha":"eb2edbcccaeda070581b4d2a0033542904b7f681","created_at":"2026-09-15T09:26:59Z","head_branch":"frontier/work-live12","event":"pull_request","path":".github/workflows/ci.yml","name":"CI/CD"},{"id":34952518481,"head_sha":"eb2edbcccaeda070581b4d2a0033542904b7f681","created_at":"2026-09-15T09:26:59Z","head_branch":"frontier/work-live12","event":"pull_request","path":".github/workflows/backend-quality.yml","name":"Backend Quality"},{"id":34952518541,"head_sha":"eb2edbcccaeda070581b4d2a0033542904b7f681","created_at":"2026-09-15T09:26:59Z","head_branch":"frontier/work-live12","event":"pull_request","path":".github/workflows/frontier-contracts.yml","name":"Frontier Contracts"},{"id":34952526563,"head_sha":"c17a989f635185f32b315bfa4e594d3568b5661d","created_at":"2026-09-15T09:27:12Z","head_branch":"frontier/work-live12","event":"pull_request","path":".github/workflows/backend-quality.yml","name":"Backend Quality"},{"id":34952526568,"head_sha":"c17a989f635185f32b315bfa4e594d3568b5661d","created_at":"2026-09-15T09:27:12Z","head_branch":"frontier/work-live12","event":"pull_request","path":".github/workflows/frontier-contracts.yml","name":"Frontier Contracts"},{"id":34952526576,"head_sha":"c17a989f635185f32b315bfa4e594d3568b5661d","created_at":"2026-09-15T09:27:12Z","head_branch":"frontier/work-live12","event":"pull_request","path":".github/workflows/ci.yml","name":"CI/CD"},{"id":34952531648,"head_sha":"5a5f393de16aaa26baed2a0ffbaba544f6968a2b","created_at":"2026-09-15T09:27:20Z","head_branch":"frontier/work-live12","event":"pull_request","path":".github/workflows/ci.yml","name":"CI/CD"},{"id":34952531743,"head_sha":"5a5f393de16aaa26baed2a0ffbaba544f6968a2b","created_at":"2026-09-15T09:27:20Z","head_branch":"frontier/work-live12","event":"pull_request","path":".github/workflows/frontier-contracts.yml","name":"Frontier Contracts"},{"id":34952531771,"head_sha":"5a5f393de16aaa26baed2a0ffbaba544f6968a2b","created_at":"2026-09-15T09:27:20Z","head_branch":"frontier/work-live12","event":"pull_request","path":".github/workflows/backend-quality.yml","name":"Backend Quality"},{"id":37539069375,"head_sha":"3048d670be32bf3720a5efcb90be20d5479060d6","created_at":"2026-10-06T22:12:20Z","head_branch":"deathmarch/vol004-runtime-supervision-latest-main","event":"pull_request","path":".github/workflows/secret-scanning.yml","name":"Secret scanning"},{"id":37539069791,"head_sha":"3048d670be32bf3720a5efcb90be20d5479060d6","created_at":"2026-10-06T22:12:20Z","head_branch":"deathmarch/vol004-runtime-supervision-latest-main","event":"pull_request","path":".github/workflows/vol004-runtime-supervision.yml","name":"VOL-004 Runtime Supervision Closure"},{"id":37642345734,"head_sha":"cd6693a1dfc4ddccac3efb9dcb8c17d601cff656","created_at":"2026-10-07T15:06:59Z","head_branch":"main","event":"workflow_run","path":".github/workflows/p2-ci-qualification.yml","name":"P2 CI Qualification Evidence"},{"id":37642355681,"head_sha":"cd6693a1dfc4ddccac3efb9dcb8c17d601cff656","created_at":"2026-10-07T15:07:13Z","head_branch":"main","event":"workflow_run","path":".github/workflows/p2-ci-qualification.yml","name":"P2 CI Qualification Evidence"},{"id":37642358530,"head_sha":"cd6693a1dfc4ddccac3efb9dcb8c17d601cff656","created_at":"2026-10-07T15:07:17Z","head_branch":"main","event":"workflow_run","path":".github/workflows/p2-ci-qualification.yml","name":"P2 CI Qualification Evidence"},{"id":37642383890,"head_sha":"cd6693a1dfc4ddccac3efb9dcb8c17d601cff656","created_at":"2026-10-07T15:09:04Z","head_branch":"main","event":"workflow_run","path":".github/workflows/p2-ci-qualification.yml","name":"P2 CI Qualification Evidence"},{"id":37642388873,"head_sha":"cd6693a1dfc4ddccac3efb9dcb8c17d601cff656","created_at":"2026-10-07T15:10:03Z","head_branch":"main","event":"workflow_run","path":".github/workflows/repair-intake.yml","name":"Automated Repair Intake"},{"id":37642398158,"head_sha":"cd6693a1dfc4ddccac3efb9dcb8c17d601cff656","created_at":"2026-10-07T15:11:13Z","head_branch":"main","event":"workflow_run","path":".github/workflows/repair-intake.yml","name":"Automated Repair Intake"},{"id":37642398159,"head_sha":"cd6693a1dfc4ddccac3efb9dcb8c17d601cff656","created_at":"2026-10-07T15:11:13Z","head_branch":"main","event":"workflow_run","path":".github/workflows/pr-automation-index.yml","name":"PR Automation Index"},{"id":37642398161,"head_sha":"cd6693a1dfc4ddccac3efb9dcb8c17d601cff656","created_at":"2026-10-07T15:11:13Z","head_branch":"main","event":"workflow_run","path":".github/workflows/automerge-control-plane.yml","name":"Auto-Merge Control Plane"},{"id":37655496094,"head_sha":"cfd5229a9c5f511ce8b8b9cf30dd4f4e622e045b","created_at":"2026-10-07T16:52:54Z","head_branch":"main","event":"workflow_run","path":".github/workflows/p2-ci-qualification.yml","name":"P2 CI Qualification Evidence"},{"id":37655496139,"head_sha":"cfd5229a9c5f511ce8b8b9cf30dd4f4e622e045b","created_at":"2026-10-07T16:52:54Z","head_branch":"main","event":"workflow_run","path":".github/workflows/autonomous-build-feedback.yml","name":"Autonomous Build Feedback"},{"id":37655521563,"head_sha":"cfd5229a9c5f511ce8b8b9cf30dd4f4e622e045b","created_at":"2026-10-07T16:55:06Z","head_branch":"main","event":"workflow_run","path":".github/workflows/autonomous-build-feedback.yml","name":"Autonomous Build Feedback"},{"id":37655522865,"head_sha":"cfd5229a9c5f511ce8b8b9cf30dd4f4e622e045b","created_at":"2026-10-07T16:55:13Z","head_branch":"main","event":"workflow_run","path":".github/workflows/autonomous-build-feedback.yml","name":"Autonomous Build Feedback"},{"id":37655530898,"head_sha":"cfd5229a9c5f511ce8b8b9cf30dd4f4e622e045b","created_at":"2026-10-07T16:56:55Z","head_branch":"main","event":"workflow_run","path":".github/workflows/p2-ci-qualification.yml","name":"P2 CI Qualification Evidence"},{"id":38320296726,"head_sha":"3293dff9480994d538a10b9e55983c65d649fb1d","created_at":"2026-10-12T23:05:35Z","head_branch":"feat/jeeves-chapter-continuity-20261013","event":"pull_request","path":".github/workflows/backend-quality.yml","name":"Backend Quality"},{"id":38320664775,"head_sha":"eb71db3ab303d20cfcfeb1f2d67770db560d44f9","created_at":"2026-10-12T23:09:53Z","head_branch":"feat/jeeves-chapter-continuity-20261013","event":"pull_request","path":".github/workflows/competitive-ai-engineering-ladder.yml","name":"Competitive AI Engineering Ladder"},{"id":38320664778,"head_sha":"eb71db3ab303d20cfcfeb1f2d67770db560d44f9","created_at":"2026-10-12T23:09:53Z","head_branch":"feat/jeeves-chapter-continuity-20261013","event":"pull_request","path":".github/workflows/ci.yml","name":"CI/CD"},{"id":38320665862,"head_sha":"eb71db3ab303d20cfcfeb1f2d67770db560d44f9","created_at":"2026-10-12T23:09:53Z","head_branch":"feat/jeeves-chapter-continuity-20261013","event":"pull_request","path":".github/workflows/ai-chat-story-continuity.yml","name":"AI Chat Story Continuity Closure"}]
PR_BY_BRANCH = {
    "frontier/work-live12": 83,
    "deathmarch/vol004-runtime-supervision-latest-main": 3377,
    "feat/jeeves-chapter-continuity-20261013": 3720,
}
ALLOWED_WORKFLOW_RUN_PATHS = frozenset({
    ".github/workflows/p2-ci-qualification.yml",
    ".github/workflows/autonomous-build-feedback.yml",
    ".github/workflows/repair-intake.yml",
    ".github/workflows/pr-automation-index.yml",
    ".github/workflows/automerge-control-plane.yml",
})
FIELDS = ("id", "created_at", "event", "head_sha", "head_branch", "path", "name")
token = os.environ.get("GH_TOKEN", "")
if (
    not token or os.environ.get("GITHUB_REPOSITORY") != REPO
    or os.environ.get("GITHUB_REF") != "refs/heads/main"
    or os.environ.get("GITHUB_EVENT_NAME") not in {"push", "workflow_run", "workflow_dispatch", "issue_comment"}
):
    raise SystemExit("Refusing non-main / unauthenticated owner clean-up")
HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": "Bearer " + token,
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "skeleton-owner-historical-tombstone-recovery",
}
start = time.monotonic()


def provider_error_evidence(raw: bytes, request_id: str | None) -> dict[str, str]:
    """Expose bounded provider diagnostics without logging credentials or raw HTML."""
    try:
        parsed = json.loads(raw.decode("utf-8", errors="replace"))
    except (ValueError, UnicodeDecodeError):
        parsed = None
    message = parsed.get("message") if isinstance(parsed, dict) else None
    if not isinstance(message, str):
        message = "unavailable; GitHub returned no JSON message"
    # GitHub request ids are useful for support and are not authentication tokens.
    request = "".join(
        char for char in str(request_id or "") if char.isascii()
        and (char.isalnum() or char in ":-")
    )[:96]
    return {"message": message[:240], "request_id": request or "unavailable"}


def request(method: str, path: str) -> tuple[int, object]:
    """Retry safe reads only; never replay an ambiguous DELETE.

    GitHub occasionally returns transient 5xx responses while its Actions
    scheduler is saturated. A DELETE may already have taken effect even if
    its response was lost, so all mutations remain strictly single-attempt.
    """
    attempts = 3 if method == "GET" else 1
    for attempt in range(attempts):
        req = urllib.request.Request(
            API_ROOT + path, headers=HEADERS,
            method=method, data=b"" if method == "DELETE" else None,
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as reply:
                body = reply.read()
                return reply.status, json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            detail = provider_error_evidence(
                exc.read(1000),
                exc.headers.get("X-GitHub-Request-Id") if exc.headers else None,
            )
            if (
                method == "GET" and exc.code in (500, 502, 503, 504)
                and attempt + 1 < attempts
            ):
                time.sleep(1 << attempt)
                continue
            return exc.code, detail
        except (urllib.error.URLError, TimeoutError) as exc:
            if method == "GET" and attempt + 1 < attempts:
                time.sleep(1 << attempt)
                continue
            raise RuntimeError(
                f"GitHub {method} {path} transport failed without reliable result"
            ) from exc
    raise RuntimeError(f"GitHub {method} {path} exhausted safe read attempts")


def get(path: str) -> object:
    status, data = request("GET", path)
    if status != 200:
        raise RuntimeError(f"Untrusted GitHub GET {path}: HTTP {status}")
    return data


def canary_proved() -> bool:
    status, run = request("GET", f"/actions/runs/{CANARY_RUN}")
    if status != 200 or not isinstance(run, dict):
        return False
    if not (
        run.get("id") == CANARY_RUN
        and run.get("head_sha") == CANARY_SHA
        and run.get("path") == ".github/workflows/historical-zero-job-canary.yml"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
    ):
        return False
    deleted, _ = request("GET", f"/actions/runs/{FIRST_TOMBSTONE}")
    return deleted == 404


def validate(row: dict[str, object]) -> bool:
    run_id = row["id"]
    status, detail = request("GET", f"/actions/runs/{run_id}")
    if status == 404:
        print(f"Already absent: {run_id}")
        return False
    if status != 200 or not isinstance(detail, dict):
        raise RuntimeError(f"Run {run_id} state not reliable: HTTP {status}")
    if any(detail.get(field) != row[field] for field in FIELDS):
        raise RuntimeError(f"Run {run_id} identity does not match archived manifest")
    if detail.get("status") != "queued" or detail.get("conclusion") is not None:
        print(f"Protected: run {run_id} no longer exactly queued")
        return False
    if detail.get("run_attempt") != 1:
        raise RuntimeError(f"Run {run_id} attempt changed")
    created = datetime.datetime.fromisoformat(
        str(row["created_at"]).replace("Z", "+00:00")
    )
    if (datetime.datetime.now(datetime.timezone.utc) - created).total_seconds() < 7 * 86400:
        raise RuntimeError(f"Run {run_id} is too new")
    if detail.get("event") == "pull_request":
        pr_number = PR_BY_BRANCH.get(str(detail.get("head_branch")))
        if not pr_number:
            raise RuntimeError(f"Run {run_id} has unknown PR branch")
        associated = get(f"/commits/{row['head_sha']}/pulls?per_page=100")
        if (
            not isinstance(associated, list) or len(associated) != 1
            or associated[0].get("number") != pr_number
        ):
            raise RuntimeError(f"Run {run_id} PR association changed")
        pr = get(f"/pulls/{pr_number}")
        if not (
            isinstance(pr, dict) and pr.get("number") == pr_number
            and pr.get("state") == "closed" and pr.get("merged_at")
            and (pr.get("base") or {}).get("repo", {}).get("full_name") == REPO
            and (pr.get("head") or {}).get("ref") == detail["head_branch"]
            and (pr.get("head") or {}).get("sha") != detail["head_sha"]
        ):
            raise RuntimeError(f"Run {run_id} merged-PR proof rejected")
    elif detail.get("event") == "workflow_run":
        if (
            detail.get("head_branch") != "main"
            or detail.get("path") not in ALLOWED_WORKFLOW_RUN_PATHS
        ):
            raise RuntimeError(f"Run {run_id} controller identity rejected")
        main = get("/git/ref/heads/main")
        if not isinstance(main, dict) or (main.get("object") or {}).get("sha") == detail["head_sha"]:
            raise RuntimeError(f"Run {run_id} not demonstrably old main")
    else:
        raise RuntimeError(f"Run {run_id} event not allowed")
    jobs = get(f"/actions/runs/{run_id}/jobs?per_page=100")
    artifacts = get(f"/actions/runs/{run_id}/artifacts?per_page=100")
    deployments = get(f"/actions/runs/{run_id}/pending_deployments")
    if not (
        isinstance(jobs, dict) and jobs.get("total_count") == 0
        and jobs.get("jobs") == []
        and isinstance(artifacts, dict) and artifacts.get("total_count") == 0
        and artifacts.get("artifacts") == []
        and deployments == []
    ):
        raise RuntimeError(f"Run {run_id} has jobs, artifacts, or approvals")
    return True


def recover_canary_in_this_worker() -> bool:
    """Avoid the two-job scheduling deadlock without weakening the canary.

    If the original canary succeeded, honor it. Otherwise the same worker
    validates and removes the exact first tombstone, verifying HTTP 404 before
    any of the thirty subsequent destructive requests.
    """
    if canary_proved():
        print("Original canary has verified success and terminal removal")
        return True
    status, original = request("GET", f"/actions/runs/{CANARY_RUN}")
    if status != 200 or not isinstance(original, dict):
        raise RuntimeError("Cannot verify original canary execution identity")
    if (
        original.get("id") != CANARY_RUN
        or original.get("head_sha") != CANARY_SHA
        or original.get("path") != ".github/workflows/historical-zero-job-canary.yml"
    ):
        raise RuntimeError("Original canary identity changed")
    if original.get("status") == "in_progress":
        print("Original canary running; avoid concurrent deletion and defer")
        return False
    status, target = request("GET", f"/actions/runs/{FIRST_TOMBSTONE}")
    if status == 404:
        # The target may have been deleted independently. Without a successful
        # archived canary, provenance cannot be proven: refuse bulk mutation.
        print("First tombstone absent but canary evidence incomplete; defer")
        return False
    if status != 200 or not isinstance(target, dict):
        raise RuntimeError("Cannot verify historical canary target")
    if target.get("updated_at") != "2026-09-15T09:26:44Z":
        raise RuntimeError("Historical canary mutation timestamp changed")
    if not validate(FIRST_ROW):
        return False
    # Race guard: original workflow might enter the runner while this one is
    # checking. Re-read its status before the mutation boundary.
    check_status, live_original = request("GET", f"/actions/runs/{CANARY_RUN}")
    if (
        check_status != 200 or not isinstance(live_original, dict)
        or live_original.get("status") == "in_progress"
    ):
        print("Cannot prove isolated canary worker; deferring")
        return False
    if not validate(FIRST_ROW):
        return False
    code, _ = request("DELETE", f"/actions/runs/{FIRST_TOMBSTONE}")
    if code != 204:
        raise RuntimeError(
            f"GitHub refused owner historical canary deletion: HTTP {code}; "
            "no other tombstone will be touched"
        )
    final_status, _ = request("GET", f"/actions/runs/{FIRST_TOMBSTONE}")
    if final_status != 404:
        raise RuntimeError(
            f"Canary DELETE accepted but not verified: HTTP {final_status}"
        )
    print(f"First historical tombstone {FIRST_TOMBSTONE} verified deleted")
    return True


def main() -> int:
    if len(MANIFEST) != 30 or len({r["id"] for r in MANIFEST}) != 30:
        raise RuntimeError("Owner manifest tampered or incomplete")
    if not recover_canary_in_this_worker():
        print("Historical delete gate remains closed; no further mutations")
        return 0
    counters = {"confirmed_deleted": 0, "already_absent_or_moved": 0,
                "provider_refusal": 0, "skipped_by_budget": 0}
    refused_ids: list[int] = []
    refusal_evidence: list[dict[str, object]] = []
    # Refusals apply to individual immutable runs, not the whole batch.
    # Preserve the refused run and continue only independently proven IDs.
    # Rate limiting or unexpected errors stop immediately.
    for index, row in enumerate(MANIFEST):
        if time.monotonic() - start > LIMIT_SECONDS or counters["confirmed_deleted"] >= MAX_DELETES:
            counters["skipped_by_budget"] += len(MANIFEST) - index
            break
        run_id = row["id"]
        if not validate(row):
            counters["already_absent_or_moved"] += 1
            continue
        # Force a fresh, identical proof at the mutation boundary.
        if not validate(row):
            counters["already_absent_or_moved"] += 1
            continue
        # An accepted DELETE is not a confirmed deletion.
        status, detail = request("DELETE", f"/actions/runs/{run_id}")
        if status in (403, 409, 422):
            reason = str(detail).lower()
            if "rate limit" in reason or "abuse" in reason or "too many requests" in reason:
                raise RuntimeError(
                    f"GitHub API rate limitation on historical run {run_id}: HTTP {status}"
                )
            # Provider rejection protects this specific run; don't retry it,
            # bypass permissions, or infer deletion from a non-204 response.
            counters["provider_refusal"] += 1
            refused_ids.append(run_id)
            evidence = {
                "run_id": run_id,
                "http_status": status,
                "provider_message": (
                    detail.get("message", "unavailable")
                    if isinstance(detail, dict) else "unavailable"
                ),
                "github_request_id": (
                    detail.get("request_id", "unavailable")
                    if isinstance(detail, dict) else "unavailable"
                ),
            }
            refusal_evidence.append(evidence)
            print(
                "Provider-refused historical run; preserving source record: "
                + json.dumps(evidence, sort_keys=True)
            )
            continue
        if status == 404:
            # Another authorized worker may have completed this exact cleanup.
            # Never claim our DELETE succeeded without its own 204 response.
            confirmed_absent, _ = request("GET", f"/actions/runs/{run_id}")
            if confirmed_absent != 404:
                raise RuntimeError(
                    f"Run {run_id} returned DELETE 404 but GET {confirmed_absent}"
                )
            counters["already_absent_or_moved"] += 1
            print(f"Independently confirmed already absent: run={run_id}")
            continue
        if status != 204:
            raise RuntimeError(
                f"Unexpected DELETE response for run {run_id}: HTTP {status}"
            )
        verify_status, _ = request("GET", f"/actions/runs/{run_id}")
        if verify_status != 404:
            raise RuntimeError(
                f"Run {run_id} DELETE acknowledged but not terminal: {verify_status}"
            )
        counters["confirmed_deleted"] += 1
        print(f"Owner deletion verified by 404: run={run_id}")
    print("Owner historical cleanup:", json.dumps(counters, sort_keys=True))
    print("Provider-refused historical IDs:", refused_ids)
    # Upload only bounded refusal diagnostics, not untrusted bodies or tokens.
    # One immutable run identity per record, useful for GitHub Actions support.
    report = os.getenv("OWNER_CLEANUP_REPORT_PATH")
    if report:
        with open(report, "w", encoding="utf-8") as output:
            json.dump(
                {"repository": REPO, "refusals": refusal_evidence,
                 "counters": counters},
                output, indent=2, sort_keys=True,
            )
            output.write("\n")
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as output:
            output.write("## Owner-ordered historical Actions cleanup\n")
            output.write("Canary: original success or independently verified first DELETE; GET 404\n")
            for key, value in counters.items():
                output.write(f"- {key}: {value}\n")
            output.write(f"- Provider-refused IDs: {refused_ids}\n")
            output.write(
                "- HTTP refusal details and request IDs: "
                "owner-historical-cleanup-refusals.json artifact\n"
            )
    return 1 if counters["provider_refusal"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
