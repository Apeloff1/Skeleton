"""Resolve a PR lifecycle signal before privileged Actions-run cleanup.

The caller is a ``workflow_run`` workflow loaded from the default branch. The
upstream signal has read-only permissions and executes no repository code. This
adapter resolves the originating same-repository PR, validates that it targets
the default branch, then delegates cancellation to ``pr_obsolete_run_drain``.
"""

from __future__ import annotations

import os
import urllib.parse
from typing import Any

if __package__:
    from .pr_obsolete_run_drain import GitHubApi, main as drain_main
else:
    from pr_obsolete_run_drain import GitHubApi, main as drain_main


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


def resolve_pr_number(
    api: GitHubApi,
    *,
    repo: str,
    hinted_number: int,
    head_sha: str,
    head_ref: str,
    default_branch: str,
) -> int | None:
    """Resolve one trusted PR, or no mutation target, for a workflow-run signal.

    Prefer immutable workflow-run hints/commit association. If GitHub drops the
    commit-to-PR association after an unmerged PR closes, recover only from an
    exact same-repository branch + base + immutable head-SHA match. If neither
    source identifies a PR, there is no privileged mutation target and cleanup
    safely becomes a no-op. Ambiguity, API failures, and contradictory identity
    remain fail-closed.
    """
    if not repo or not head_ref or not head_sha or not default_branch:
        raise RuntimeError("incomplete workflow_run PR identity")
    if head_ref == default_branch:
        raise RuntimeError("refusing cleanup for the default branch")

    if hinted_number > 0:
        status, payload, _ = api.request(f"/repos/{repo}/pulls/{hinted_number}")
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError(f"failed to resolve hinted PR #{hinted_number}: HTTP {status}")
        if not _matches_signal(
            payload,
            repo=repo,
            head_ref=head_ref,
            default_branch=default_branch,
        ):
            raise RuntimeError("workflow_run PR hint failed same-repository/base validation")
        return hinted_number

    quoted_sha = urllib.parse.quote(head_sha, safe="")
    status, payload, _ = api.request(f"/repos/{repo}/commits/{quoted_sha}/pulls")
    if status != 200 or not isinstance(payload, list):
        raise RuntimeError(f"failed to resolve PR from workflow_run head: HTTP {status}")

    candidates = {
        int(item.get("number") or 0)
        for item in payload
        if isinstance(item, dict)
        and _matches_signal(
            item,
            repo=repo,
            head_ref=head_ref,
            default_branch=default_branch,
        )
    }
    candidates.discard(0)
    if len(candidates) == 1:
        return next(iter(candidates))
    if len(candidates) > 1:
        raise RuntimeError(
            "workflow_run head resolved to multiple trusted PRs via commit association "
            f"(matches={sorted(candidates)})"
        )

    owner, separator, _ = repo.partition("/")
    if not separator or not owner:
        raise RuntimeError("invalid repository identity for PR history lookup")
    quoted_head = urllib.parse.quote(f"{owner}:{head_ref}", safe="")
    quoted_base = urllib.parse.quote(default_branch, safe="")
    history_path = (
        f"/repos/{repo}/pulls?state=all&head={quoted_head}&base={quoted_base}"
        "&sort=updated&direction=desc&per_page=100"
    )
    status, history, _ = api.request(history_path)
    if status != 200 or not isinstance(history, list):
        raise RuntimeError(f"failed to resolve PR from workflow_run branch history: HTTP {status}")

    historical_candidates = {
        int(item.get("number") or 0)
        for item in history
        if isinstance(item, dict)
        and _matches_signal(
            item,
            repo=repo,
            head_ref=head_ref,
            default_branch=default_branch,
        )
        and _head_sha(item) == head_sha
    }
    historical_candidates.discard(0)
    if len(historical_candidates) == 1:
        return next(iter(historical_candidates))
    if len(historical_candidates) > 1:
        raise RuntimeError(
            "workflow_run head resolved to multiple trusted PRs via branch history "
            f"(matches={sorted(historical_candidates)})"
        )
    return None


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
    return live_head_sha == signal_head_sha


def main() -> int:
    token = os.environ["GH_TOKEN"]
    repo = os.environ["REPO"]
    head_repo = os.environ["EVENT_HEAD_REPO"]
    head_ref = os.environ["EVENT_HEAD_REF"]
    head_sha = os.environ["EVENT_HEAD_SHA"]
    default_branch = os.environ["DEFAULT_BRANCH"]
    hinted = int(os.environ.get("PR_NUMBER") or "0")

    if head_repo != repo:
        print("drain failed: refusing workflow_run cleanup for a cross-repository PR")
        return 1

    api = GitHubApi(token)
    try:
        pr_number = resolve_pr_number(
            api,
            repo=repo,
            hinted_number=hinted,
            head_sha=head_sha,
            head_ref=head_ref,
            default_branch=default_branch,
        )
        if pr_number is None:
            print(
                "obsolete-run drain skipped: workflow_run head no longer "
                "resolves to a trusted pull request"
            )
            return 0
        if not live_pr_head_converged(
            api,
            repo=repo,
            pr_number=pr_number,
            signal_head_sha=head_sha,
        ):
            print(
                "obsolete-run drain deferred: live pull-request head has not "
                "converged to the lifecycle signal head"
            )
            return 0
    except RuntimeError as exc:
        print(f"drain failed: {exc}")
        return 1

    os.environ["PR_NUMBER"] = str(pr_number)
    os.environ["PR_ACTION"] = "synchronize"
    os.environ.setdefault("EVENT_BEFORE_SHA", "")
    return drain_main()


if __name__ == "__main__":
    raise SystemExit(main())
