from __future__ import annotations

from pathlib import Path

from scripts.pr_obsolete_run_sweep import sweep

REPO = "Apeloff1/Skeleton"
DEFAULT_BRANCH = "main"
WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pr-obsolete-run-drain.yml"


class FakeApi:
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[tuple[str, str]] = []
        self.sleeps: list[float] = []

    def request(self, path: str, *, method: str = "GET"):
        self.calls.append((method, path))
        return self.handler(method, path)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def run(
    run_id: int,
    sha: str,
    *,
    branch: str = "feature/sweep",
    event: str = "pull_request",
    head_repo: str = REPO,
    pulls=None,
) -> dict:
    return {
        "id": run_id,
        "event": event,
        "head_branch": branch,
        "head_sha": sha,
        "head_repository": {"full_name": head_repo},
        "pull_requests": [] if pulls is None else pulls,
    }


def pr(
    number: int,
    *,
    state: str,
    head_sha: str,
    branch: str = "feature/sweep",
) -> dict:
    return {
        "number": number,
        "state": state,
        "head": {
            "ref": branch,
            "sha": head_sha,
            "repo": {"full_name": REPO},
        },
        "base": {"ref": DEFAULT_BRANCH},
    }


def handler_for(
    queued_runs: list[dict],
    *,
    associations: dict[str, list[int]],
    prs: dict[int, dict],
):
    def handler(method: str, path: str):
        if method == "GET" and "/actions/runs?" in path:
            payload = queued_runs if "status=queued" in path else []
            return 200, {"workflow_runs": payload}, {}
        if method == "GET" and "/commits/" in path and path.endswith("/pulls"):
            sha = path.split("/commits/", 1)[1].rsplit("/pulls", 1)[0]
            return 200, [{"number": number} for number in associations.get(sha, [])], {}
        if method == "GET" and "/pulls/" in path:
            number = int(path.rsplit("/", 1)[1])
            return 200, prs[number], {}
        if method == "POST" and path.endswith("/cancel"):
            return 202, None, {}
        raise AssertionError(f"unexpected network call: {method} {path}")

    return handler


def test_closed_pr_backlog_run_is_cancelled() -> None:
    api = FakeApi(
        handler_for(
            [run(10, "old")],
            associations={"old": [593]},
            prs={593: pr(593, state="closed", head_sha="old")},
        )
    )

    summary = sweep(
        api,
        repo=REPO,
        current_run_id=999,
        default_branch=DEFAULT_BRANCH,
    )

    assert summary["obsolete"] == 1
    assert summary["accepted"] == 1
    assert ("POST", f"/repos/{REPO}/actions/runs/10/cancel") in api.calls


def test_current_open_pr_head_is_preserved() -> None:
    api = FakeApi(
        handler_for(
            [run(20, "current")],
            associations={"current": [700]},
            prs={700: pr(700, state="open", head_sha="current")},
        )
    )

    summary = sweep(
        api,
        repo=REPO,
        current_run_id=999,
        default_branch=DEFAULT_BRANCH,
    )

    assert summary["authoritative"] == 1
    assert summary["obsolete"] == 0
    assert not any(method == "POST" for method, _ in api.calls)


def test_stale_open_pr_head_is_cancelled() -> None:
    api = FakeApi(
        handler_for(
            [run(30, "old")],
            associations={"old": [701]},
            prs={701: pr(701, state="open", head_sha="new")},
        )
    )

    summary = sweep(
        api,
        repo=REPO,
        current_run_id=999,
        default_branch=DEFAULT_BRANCH,
    )

    assert summary["obsolete"] == 1
    assert summary["accepted"] == 1


def test_default_branch_cross_repo_and_unclassified_runs_fail_closed() -> None:
    api = FakeApi(
        handler_for(
            [
                run(40, "main-sha", branch="main"),
                run(41, "fork-sha", head_repo="someone/fork"),
                run(42, "unknown"),
            ],
            associations={"unknown": []},
            prs={},
        )
    )

    summary = sweep(
        api,
        repo=REPO,
        current_run_id=999,
        default_branch=DEFAULT_BRANCH,
    )

    assert summary["eligible"] == 1
    assert summary["unclassified"] == 1
    assert summary["obsolete"] == 0
    assert not any(method == "POST" for method, _ in api.calls)


def test_sweep_cap_bounds_mutation_per_run() -> None:
    api = FakeApi(
        handler_for(
            [run(50, "a"), run(51, "b")],
            associations={"a": [800], "b": [801]},
            prs={
                800: pr(800, state="closed", head_sha="a"),
                801: pr(801, state="closed", head_sha="b"),
            },
        )
    )

    summary = sweep(
        api,
        repo=REPO,
        current_run_id=999,
        default_branch=DEFAULT_BRANCH,
        max_cancellations=1,
    )

    assert summary["obsolete"] == 2
    assert summary["accepted"] == 1
    assert summary["over_cap"] == 1


def test_workflow_has_periodic_and_rollout_backlog_reconciliation() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "schedule:" in text
    assert "*/10 * * * *" in text
    assert "push:" in text
    assert "backend/scripts/pr_obsolete_run_sweep.py" in text
    assert "python backend/scripts/pr_obsolete_run_sweep.py" in text
