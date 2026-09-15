from __future__ import annotations

from scripts.pr_obsolete_run_drain import (
    CancelResult,
    DrainContext,
    belongs_to_pr,
    cancel_run,
    drain,
)

REPO = "Apeloff1/Skeleton"


class FakeApi:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []
        self.sleeps = []

    def request(self, path: str, *, method: str = "GET"):
        self.calls.append((method, path))
        return self.handler(method, path)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def context(**overrides) -> DrainContext:
    values = {
        "repo": REPO,
        "current_run_id": 999,
        "pr_number": 556,
        "event_action": "synchronize",
        "event_head_repo": REPO,
        "event_head_ref": "feature/drain",
        "event_head_sha": "new",
        "event_before_sha": "old",
        "default_branch": "main",
    }
    values.update(overrides)
    return DrainContext(**values)


def pr(state: str = "open", sha: str = "new") -> dict:
    return {
        "number": 556,
        "state": state,
        "head": {
            "ref": "feature/drain",
            "sha": sha,
            "repo": {"full_name": REPO},
        },
    }


def run(
    run_id: int,
    sha: str,
    *,
    event: str = "pull_request",
    branch: str = "feature/drain",
    pulls=None,
    head_repo: str = REPO,
) -> dict:
    return {
        "id": run_id,
        "event": event,
        "head_branch": branch,
        "head_sha": sha,
        "head_repository": {"full_name": head_repo},
        "pull_requests": [] if pulls is None else pulls,
    }


def no_network(method: str, path: str):
    raise AssertionError(f"unexpected network call: {method} {path}")


def test_empty_pull_requests_matches_normal_run_via_trusted_event_sha() -> None:
    api = FakeApi(no_network)
    assert belongs_to_pr(
        api,
        run(1, "old"),
        context=context(),
        pr=pr(),
        known_pr_shas={"new"},
        commit_link_cache={},
    )


def test_empty_pull_requests_matches_dynamic_run_via_commit_association() -> None:
    def handler(method: str, path: str):
        assert method == "GET"
        assert path.endswith("/commits/older/pulls")
        return 200, [{"number": 556}], {}

    api = FakeApi(handler)
    assert belongs_to_pr(
        api,
        run(2, "older", event="dynamic"),
        context=context(event_before_sha=""),
        pr=pr(),
        known_pr_shas={"new"},
        commit_link_cache={},
    )


def test_default_branch_is_never_a_pr_cleanup_target_even_with_explicit_link() -> None:
    api = FakeApi(no_network)
    assert not belongs_to_pr(
        api,
        run(3, "new", branch="main", pulls=[{"number": 556}]),
        context=context(),
        pr=pr(),
        known_pr_shas={"new"},
        commit_link_cache={},
    )


def test_fallback_requires_same_repository() -> None:
    api = FakeApi(no_network)
    assert not belongs_to_pr(
        api,
        run(4, "old", head_repo="someone/fork"),
        context=context(),
        pr=pr(),
        known_pr_shas={"old", "new"},
        commit_link_cache={},
    )


def _drain_handler(state: str, queued_runs: list[dict]):
    def handler(method: str, path: str):
        if method == "GET" and path == f"/repos/{REPO}/pulls/556":
            return 200, pr(state=state), {}
        if method == "GET" and path.startswith(f"/repos/{REPO}/pulls/556/commits?"):
            return 200, [{"sha": "old"}, {"sha": "new"}], {}
        if method == "GET" and "/actions/runs?" in path:
            if "status=queued" in path:
                return 200, {"workflow_runs": queued_runs}, {}
            return 200, {"workflow_runs": []}, {}
        if method == "POST" and path.endswith("/cancel"):
            return 202, None, {}
        raise AssertionError(f"unexpected network call: {method} {path}")

    return handler


def test_synchronize_cancels_stale_head_and_preserves_current_head() -> None:
    api = FakeApi(_drain_handler("open", [run(10, "old"), run(11, "new")]))
    summary = drain(api, context())
    assert summary["inspected"] == 2
    assert summary["selected"] == 1
    assert summary["accepted"] == 1
    assert ("POST", f"/repos/{REPO}/actions/runs/10/cancel") in api.calls
    assert ("POST", f"/repos/{REPO}/actions/runs/11/cancel") not in api.calls


def test_closed_pr_cancels_current_and_stale_runs() -> None:
    api = FakeApi(
        _drain_handler(
            "closed",
            [run(20, "old"), run(21, "new", event="dynamic")],
        )
    )
    summary = drain(api, context(event_action="closed"))
    assert summary["selected"] == 2
    assert summary["accepted"] == 2


def test_live_pr_state_wins_over_stale_closed_event_after_reopen() -> None:
    api = FakeApi(_drain_handler("open", [run(30, "old"), run(31, "new")]))
    summary = drain(api, context(event_action="closed"))
    assert summary["live_state"] == "open"
    assert summary["selected"] == 1
    assert ("POST", f"/repos/{REPO}/actions/runs/31/cancel") not in api.calls


def test_normal_cancel_transients_fall_back_to_force_cancel() -> None:
    cancel_attempts = 0

    def handler(method: str, path: str):
        nonlocal cancel_attempts
        if method == "POST" and path.endswith("/cancel") and not path.endswith("/force-cancel"):
            cancel_attempts += 1
            return 503, {"message": "temporary"}, {}
        if method == "POST" and path.endswith("/force-cancel"):
            return 202, None, {}
        raise AssertionError(f"unexpected network call: {method} {path}")

    api = FakeApi(handler)
    result = cancel_run(api, REPO, 40)
    assert result == CancelResult("forced", 202)
    assert cancel_attempts == 3
    assert api.sleeps == [1.0, 2.0]


def test_422_is_only_benign_when_run_is_confirmed_completed() -> None:
    def handler(method: str, path: str):
        if method == "POST" and path.endswith("/cancel") and not path.endswith("/force-cancel"):
            return 422, {"message": "cannot cancel"}, {}
        if method == "GET" and path.endswith("/actions/runs/50"):
            return 200, {"status": "completed"}, {}
        raise AssertionError(f"unexpected network call: {method} {path}")

    api = FakeApi(handler)
    assert cancel_run(api, REPO, 50) == CancelResult("moved", 422)
    assert not any(path.endswith("/force-cancel") for _, path in api.calls)


def test_422_on_live_run_uses_force_cancel() -> None:
    def handler(method: str, path: str):
        if method == "POST" and path.endswith("/cancel") and not path.endswith("/force-cancel"):
            return 422, {"message": "cannot cancel"}, {}
        if method == "GET" and path.endswith("/actions/runs/60"):
            return 200, {"status": "in_progress"}, {}
        if method == "POST" and path.endswith("/force-cancel"):
            return 202, None, {}
        raise AssertionError(f"unexpected network call: {method} {path}")

    api = FakeApi(handler)
    assert cancel_run(api, REPO, 60) == CancelResult("forced", 202)


def test_cross_repository_context_fails_closed() -> None:
    api = FakeApi(no_network)
    try:
        drain(api, context(event_head_repo="someone/fork"))
    except RuntimeError as exc:
        assert "cross-repository" in str(exc)
    else:
        raise AssertionError("cross-repository cleanup should fail closed")
