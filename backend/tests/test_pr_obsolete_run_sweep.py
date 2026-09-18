from __future__ import annotations

from pathlib import Path

import pytest

from scripts import pr_obsolete_run_sweep as sweep_module
from scripts.pr_obsolete_run_drain import COMMIT_PULLS_PAGE_SIZE
from scripts.pr_obsolete_run_sweep import _commit_pr_numbers, sweep

REPO = "Apeloff1/Skeleton"
DEFAULT_BRANCH = "main"
OLD_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
NEW_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
CURRENT_SHA = "cccccccccccccccccccccccccccccccccccccccc"
UNKNOWN_SHA = "dddddddddddddddddddddddddddddddddddddddd"
SHA_A = "1111111111111111111111111111111111111111"
SHA_B = "2222222222222222222222222222222222222222"
STUCK_SHA = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
PAGED_SHA = "ffffffffffffffffffffffffffffffffffffffff"
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
        if method == "GET" and "/commits/" in path and "/pulls" in path.split("/commits/", 1)[1]:
            sha = path.split("/commits/", 1)[1].split("/pulls", 1)[0]
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
            [run(10, OLD_SHA)],
            associations={OLD_SHA: [593]},
            prs={593: pr(593, state="closed", head_sha=OLD_SHA)},
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
            [run(20, CURRENT_SHA)],
            associations={CURRENT_SHA: [700]},
            prs={700: pr(700, state="open", head_sha=CURRENT_SHA)},
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
            [run(30, OLD_SHA)],
            associations={OLD_SHA: [701]},
            prs={701: pr(701, state="open", head_sha=NEW_SHA)},
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


def test_closed_pr_reopened_on_run_sha_is_preserved_before_cancel() -> None:
    pr_reads = 0

    def handler(method: str, path: str):
        nonlocal pr_reads
        if method == "GET" and "/actions/runs?" in path:
            payload = [run(31, OLD_SHA)] if "status=queued" in path else []
            return 200, {"workflow_runs": payload}, {}
        if method == "GET" and f"/commits/{OLD_SHA}/pulls" in path:
            return 200, [{"number": 702}], {}
        if method == "GET" and path.endswith("/pulls/702"):
            pr_reads += 1
            current = (
                pr(702, state="closed", head_sha=OLD_SHA)
                if pr_reads == 1
                else pr(702, state="open", head_sha=OLD_SHA)
            )
            return 200, current, {}
        if method == "POST" and path.endswith("/cancel"):
            raise AssertionError("reopened authoritative run must not be cancelled")
        raise AssertionError(f"unexpected network call: {method} {path}")

    summary = sweep(
        FakeApi(handler),
        repo=REPO,
        current_run_id=999,
        default_branch=DEFAULT_BRANCH,
    )

    assert summary["obsolete"] == 1
    assert summary["race_preserved"] == 1
    assert summary["authoritative"] == 1
    assert summary["accepted"] == 0
    assert pr_reads == 2


def test_stale_open_pr_moved_back_to_run_sha_is_preserved_before_cancel() -> None:
    pr_reads = 0

    def handler(method: str, path: str):
        nonlocal pr_reads
        if method == "GET" and "/actions/runs?" in path:
            payload = [run(32, OLD_SHA)] if "status=queued" in path else []
            return 200, {"workflow_runs": payload}, {}
        if method == "GET" and f"/commits/{OLD_SHA}/pulls" in path:
            return 200, [{"number": 703}], {}
        if method == "GET" and path.endswith("/pulls/703"):
            pr_reads += 1
            head_sha = NEW_SHA if pr_reads == 1 else OLD_SHA
            return 200, pr(703, state="open", head_sha=head_sha), {}
        if method == "POST" and path.endswith("/cancel"):
            raise AssertionError("head-rollback authoritative run must not be cancelled")
        raise AssertionError(f"unexpected network call: {method} {path}")

    summary = sweep(
        FakeApi(handler),
        repo=REPO,
        current_run_id=999,
        default_branch=DEFAULT_BRANCH,
    )

    assert summary["obsolete"] == 1
    assert summary["race_preserved"] == 1
    assert summary["authoritative"] == 1
    assert summary["accepted"] == 0
    assert pr_reads == 2


def test_default_branch_cross_repo_and_unclassified_runs_fail_closed() -> None:
    api = FakeApi(
        handler_for(
            [
                run(40, "main-sha", branch="main"),
                run(41, "fork-sha", head_repo="someone/fork"),
                run(42, UNKNOWN_SHA),
            ],
            associations={UNKNOWN_SHA: []},
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
            [run(50, SHA_A), run(51, SHA_B)],
            associations={SHA_A: [800], SHA_B: [801]},
            prs={
                800: pr(800, state="closed", head_sha=SHA_A),
                801: pr(801, state="closed", head_sha=SHA_B),
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


def test_periodic_sweep_defers_provider_stuck_409_after_force_cancel() -> None:
    """A live run rejected by both cancel endpoints is retried next sweep."""

    def handler(method: str, path: str):
        if method == "GET" and "/actions/runs?" in path:
            payload = [run(60, STUCK_SHA)] if "status=queued" in path else []
            return 200, {"workflow_runs": payload}, {}
        if method == "GET" and f"/commits/{STUCK_SHA}/pulls" in path:
            return 200, [{"number": 900}], {}
        if method == "GET" and path.endswith("/pulls/900"):
            return 200, pr(900, state="closed", head_sha=STUCK_SHA), {}
        if method == "POST" and (
            path.endswith("/cancel") or path.endswith("/force-cancel")
        ):
            return 409, {"message": "Conflict"}, {}
        if method == "GET" and path.endswith("/actions/runs/60"):
            return 200, {"status": "queued"}, {}
        raise AssertionError(f"unexpected network call: {method} {path}")

    api = FakeApi(handler)
    summary = sweep(
        api,
        repo=REPO,
        current_run_id=999,
        default_branch=DEFAULT_BRANCH,
    )

    assert summary["obsolete"] == 1
    assert summary["deferred"] == 1
    assert summary["failed"] == 0
    assert ("POST", f"/repos/{REPO}/actions/runs/60/cancel") in api.calls
    assert ("POST", f"/repos/{REPO}/actions/runs/60/force-cancel") in api.calls


def test_main_keeps_deferred_sweep_green_but_terminal_failure_red(monkeypatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setenv("REPO", REPO)
    monkeypatch.setenv("CURRENT_RUN_ID", "999")
    monkeypatch.setenv("DEFAULT_BRANCH", DEFAULT_BRANCH)
    monkeypatch.setattr(sweep_module, "GitHubApi", lambda _token: object())
    monkeypatch.setattr(sweep_module, "_write_summary", lambda _summary: None)
    monkeypatch.setattr(
        sweep_module,
        "sweep",
        lambda *_args, **_kwargs: {"failed": 0, "deferred": 1},
    )
    assert sweep_module.main() == 0

    monkeypatch.setattr(
        sweep_module,
        "sweep",
        lambda *_args, **_kwargs: {"failed": 1, "deferred": 0},
    )
    assert sweep_module.main() == 1


def test_workflow_has_periodic_and_rollout_backlog_reconciliation() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "schedule:" in text
    assert "*/10 * * * *" in text
    assert "push:" in text
    assert "backend/scripts/pr_obsolete_run_sweep.py" in text
    assert "python backend/scripts/pr_obsolete_run_sweep.py" in text


def test_commit_pr_numbers_keep_later_pages() -> None:
    def handler(method: str, path: str):
        assert method == "GET"
        if path.endswith("page=1"):
            return 200, [{"number": n} for n in range(1, COMMIT_PULLS_PAGE_SIZE + 1)], {}
        if path.endswith("page=2"):
            return 200, [{"number": 910}], {}
        raise AssertionError(path)

    numbers = _commit_pr_numbers(
        FakeApi(handler),
        repo=REPO,
        sha=PAGED_SHA,
        cache={},
    )
    assert 1 in numbers
    assert 910 in numbers


def test_commit_pr_numbers_scan_bound_fails_closed() -> None:
    def handler(method: str, path: str):
        return 200, [{"number": n} for n in range(1, COMMIT_PULLS_PAGE_SIZE + 1)], {}

    with pytest.raises(RuntimeError, match="bounded identity scan"):
        _commit_pr_numbers(
            FakeApi(handler),
            repo=REPO,
            sha=PAGED_SHA,
            cache={},
        )


def test_malformed_run_sha_is_not_looked_up() -> None:
    api = FakeApi(
        handler_for(
            [run(70, "abc123")],
            associations={},
            prs={},
        )
    )

    summary = sweep(
        api,
        repo=REPO,
        current_run_id=999,
        default_branch=DEFAULT_BRANCH,
    )

    assert summary["eligible"] == 0
    assert summary["obsolete"] == 0
    assert not any("/commits/" in path for _, path in api.calls)
    assert not any(method == "POST" for method, _ in api.calls)


def test_open_pr_malformed_live_sha_is_unclassified() -> None:
    api = FakeApi(
        handler_for(
            [run(71, OLD_SHA)],
            associations={OLD_SHA: [704]},
            prs={704: pr(704, state="open", head_sha="not-an-oid")},
        )
    )

    summary = sweep(
        api,
        repo=REPO,
        current_run_id=999,
        default_branch=DEFAULT_BRANCH,
    )

    assert summary["unclassified"] >= 1
    assert summary["obsolete"] == 0
    assert not any(method == "POST" for method, _ in api.calls)


def test_uppercase_live_head_sha_is_authoritative() -> None:
    api = FakeApi(
        handler_for(
            [run(72, CURRENT_SHA)],
            associations={CURRENT_SHA: [705]},
            prs={705: pr(705, state="open", head_sha=CURRENT_SHA.upper())},
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


def test_sweep_commit_association_bound_aborts_entire_scan() -> None:
    def handler(method: str, path: str):
        if method == "GET" and "/actions/runs?" in path:
            payload = [run(80, PAGED_SHA)] if "status=queued" in path else []
            return 200, {"workflow_runs": payload}, {}
        if method == "GET" and f"/commits/{PAGED_SHA}/pulls" in path:
            return 200, [{"number": n} for n in range(1, COMMIT_PULLS_PAGE_SIZE + 1)], {}
        raise AssertionError(f"unexpected network call: {method} {path}")

    with pytest.raises(RuntimeError, match="bounded identity scan"):
        sweep(
            FakeApi(handler),
            repo=REPO,
            current_run_id=999,
            default_branch=DEFAULT_BRANCH,
        )
