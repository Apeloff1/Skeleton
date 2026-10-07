"""Resolve PR lifecycle signals before privileged Actions-run cleanup.

The caller is a ``workflow_run`` workflow loaded from the default branch. The
upstream signal has read-only permissions and executes no repository code. This
adapter resolves every originating same-repository PR, validates that each
targets the default branch, then delegates cancellation to
``pr_obsolete_run_drain``.
"""

from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any

if __package__:
    from .pr_obsolete_run_drain import (
        GitHubApi,
        canonical_commit_oid,
        list_commit_associated_pulls,
        main as drain_main,
    )
else:
    from pr_obsolete_run_drain import (
        GitHubApi,
        canonical_commit_oid,
        list_commit_associated_pulls,
        main as drain_main,
    )


MAX_HISTORY_PAGES = 10
HISTORY_PAGE_SIZE = 100


def _repo_full_name(obj: Any) -> str:
    return str((obj or {}).get("full_name") or "")


def _matches_signal(
    pr: dict[str, Any],
    *,
    repo: str,
    head_ref: str,
    default_branch: str,
) -> bool:
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    return (
        int(pr.get("number") or 0) > 0
        and _repo_full_name(head.get("repo")) == repo
        and str(head.get("ref") or "") == head_ref
        and str(base.get("ref") or "") == default_branch
    )


def _head_sha(pr: dict[str, Any]) -> str:
    return str((pr.get("head") or {}).get("sha") or "")


def parse_pr_hints_json(raw: str) -> list[int]:
    """Parse GitHub's workflow_run.pull_requests numbers from env JSON.

    The event array is capped and often empty; hints never replace SHA/branch
    identity. Fail closed on malformed payloads so a truncated expression cannot
    silently drain the wrong PR.
    """
    text = (raw or "").strip()
    if not text or text in {"null", "[]"}:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("invalid workflow_run PR hint JSON") from exc
    if not isinstance(payload, list):
        raise RuntimeError("workflow_run PR hints must be a JSON array")
    numbers: dict[int, None] = {}
    for item in payload:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise RuntimeError(f"invalid workflow_run PR hint: {item!r}")
        numbers[item] = None
    return list(numbers)


def _list_branch_history(
    api: GitHubApi,
    *,
    repo: str,
    owner: str,
    head_ref: str,
    default_branch: str,
) -> list[dict[str, Any]]:
    """List a bounded, complete prefix of matching PR history.

    Identity recovery must not silently trust only GitHub's first page. Scan up
    to 1,000 branch/base matches and fail closed if that bound is exhausted,
    because an unseen later page could contain another exact head-SHA match.
    """
    history: list[dict[str, Any]] = []
    for page in range(1, MAX_HISTORY_PAGES + 1):
        query = urllib.parse.urlencode(
            {
                "state": "all",
                "head": f"{owner}:{head_ref}",
                "base": default_branch,
                "sort": "updated",
                "direction": "desc",
                "per_page": HISTORY_PAGE_SIZE,
                "page": page,
            }
        )
        status, payload, _ = api.request(f"/repos/{repo}/pulls?{query}")
        if status != 200 or not isinstance(payload, list):
            raise RuntimeError(
                "failed to resolve PR from workflow_run branch history: "
                f"HTTP {status}"
            )
        history.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < HISTORY_PAGE_SIZE:
            return history

    raise RuntimeError(
        "workflow_run branch history exceeded bounded 1000-entry identity scan"
    )


def resolve_pr_numbers(
    api: GitHubApi,
    *,
    repo: str,
    hinted_numbers: list[int],
    head_sha: str,
    head_ref: str,
    default_branch: str,
) -> list[int]:
    """Resolve every trusted PR for a workflow-run lifecycle signal.

    Prefer immutable workflow-run hints/commit association. If GitHub drops the
    commit-to-PR association after an unmerged PR closes, recover only from an
    exact same-repository branch + base + immutable head-SHA match. If neither
    source identifies a PR, there is no privileged mutation target and cleanup
    safely becomes a no-op. API failures, malformed hints, and exhausted
    pagination remain fail-closed. Multiple trusted matches are all drained
    because they share the completing head.
    """
    if not repo or not head_ref or not head_sha or not default_branch:
        raise RuntimeError("incomplete workflow_run PR identity")
    if head_ref == default_branch:
        raise RuntimeError("refusing cleanup for the default branch")
    head_sha = canonical_commit_oid(head_sha)

    ordered: dict[int, None] = {}

    def consider(pr: Any) -> None:
        if not isinstance(pr, dict):
            return
        if not _matches_signal(
            pr,
            repo=repo,
            head_ref=head_ref,
            default_branch=default_branch,
        ):
            return
        number = int(pr.get("number") or 0)
        if number > 0:
            ordered[number] = None

    for hinted in hinted_numbers:
        if hinted <= 0:
            raise RuntimeError(f"invalid hinted PR number: {hinted}")
        status, payload, _ = api.request(f"/repos/{repo}/pulls/{hinted}")
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError(f"failed to resolve hinted PR #{hinted}: HTTP {status}")
        consider(payload)

    for item in list_commit_associated_pulls(api, repo, head_sha):
        consider(item)

    if ordered:
        return list(ordered)

    owner, separator, _ = repo.partition("/")
    if not separator or not owner:
        raise RuntimeError("invalid repository identity for PR history lookup")
    history = _list_branch_history(
        api,
        repo=repo,
        owner=owner,
        head_ref=head_ref,
        default_branch=default_branch,
    )

    for item in history:
        recorded = _head_sha(item)
        try:
            if canonical_commit_oid(recorded) == head_sha:
                consider(item)
        except RuntimeError:
            continue
    return list(ordered)


def live_pr_head_converged(
    api: GitHubApi,
    *,
    repo: str,
    pr_number: int,
    signal_head_sha: str,
) -> bool:
    """Return whether live PR state is safe to use for this lifecycle signal."""
    status, payload, _ = api.request(f"/repos/{repo}/pulls/{pr_number}")
    if status != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"failed to refresh PR #{pr_number}: HTTP {status}")

    state = str(payload.get("state") or "").lower()
    if state == "closed":
        return True
    if state != "open":
        raise RuntimeError(f"PR #{pr_number} response has unknown state {state!r}")

    head = payload.get("head") or {}
    live_head_sha = str(head.get("sha") or "")
    if not live_head_sha:
        raise RuntimeError(f"open PR #{pr_number} response is missing head.sha")
    live_head_sha = canonical_commit_oid(live_head_sha)
    return live_head_sha == canonical_commit_oid(signal_head_sha)


def _drain_one(pr_number: int) -> int:
    os.environ["PR_NUMBER"] = str(pr_number)
    os.environ["PR_ACTION"] = "synchronize"
    os.environ.setdefault("EVENT_BEFORE_SHA", "")
    return drain_main()


def main() -> int:
    token = os.environ["GH_TOKEN"]
    repo = os.environ["REPO"]
    head_repo = os.environ["EVENT_HEAD_REPO"]
    head_ref = os.environ["EVENT_HEAD_REF"]
    head_sha = os.environ["EVENT_HEAD_SHA"]
    default_branch = os.environ["DEFAULT_BRANCH"]

    if head_repo != repo:
        print("drain failed: refusing workflow_run cleanup for a cross-repository PR")
        return 1

    try:
        hinted_numbers = parse_pr_hints_json(os.environ.get("WORKFLOW_RUN_PR_HINTS", ""))
        head_sha = canonical_commit_oid(head_sha)
        os.environ["EVENT_HEAD_SHA"] = head_sha
    except RuntimeError as exc:
        print(f"drain failed: {exc}")
        return 1

    api = GitHubApi(token)
    try:
        pr_numbers = resolve_pr_numbers(
            api,
            repo=repo,
            hinted_numbers=hinted_numbers,
            head_sha=head_sha,
            head_ref=head_ref,
            default_branch=default_branch,
        )
        if not pr_numbers:
            print(
                "obsolete-run drain skipped: workflow_run head no longer "
                "resolves to a trusted pull request"
            )
            return 0

        failures = 0
        for pr_number in pr_numbers:
            if not live_pr_head_converged(
                api,
                repo=repo,
                pr_number=pr_number,
                signal_head_sha=head_sha,
            ):
                print(
                    "obsolete-run drain deferred: live pull-request head has not "
                    f"converged to the lifecycle signal head for #{pr_number}"
                )
                continue
            if _drain_one(pr_number) != 0:
                failures += 1
    except RuntimeError as exc:
        print(f"drain failed: {exc}")
        return 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
