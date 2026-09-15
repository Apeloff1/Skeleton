from __future__ import annotations

from pathlib import Path

from scripts.pr_obsolete_run_drain import (
    CancelResult,
    DrainContext,
    belongs_to_pr,
    cancel_run,
    drain,
    resolve_context_from_trigger,
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
        "pr_number": 609,
        "event_action": "synchronize",
        "event_head_repo": REPO,
        "event_head_ref": "feature/drain",
        "event_head_sha": "new",
        "event_before_sha": "old",
        "default_branch": "main",
    }
    values.update(overrides)
    return DrainContext(**values)


def pr(state: str = "open", sha: str = "new", *, repo: str = REPO) -> dict:
    return {
        "number": 609,
        "state": state,
        "head": {"ref": "feature/drain", "sha": sha, "repo": {"full_name": repo}},
        "base": {"ref": "main"},
    }


def trigger_run(*, pulls=None, head_repo: str = REPO, sha: str = "new") -> dict:
    return {
        "id": 700,
        "event": "pull_request",
        "path": ".github/workflows/pr-lifecycle-signal.yml",
        "repository": {"full_name": REPO},
        "head_repository": {"full_name": head_repo},
        "head_branch": "feature/drain",
        "head_sha": sha,
        "pull_requests": [] if pulls is None else pulls,
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


def _set_env(monkeypatch) -> None:
    monkeypatch.setenv("REPO", REPO)
    monkeypatch.setenv("DEFAULT_BRANCH", "main")
    monkeypatch.setenv("CURRENT_RUN_ID", "999")
    monkeypatch.setenv("TRIGGER_RUN_ID", "700")


def test_workflow_run_explicit_pr_link_resolves_context(monkeypatch) -> None:
    _set_env(monkeypatch)

    def handler(method: str, path: str):
        assert method == "GET"
        if path.endswith("/actions/runs/700"):
            return 200, trigger_run(pulls=[{"number": 609}]), {}
        if path.endswith("/pulls/609"):
            return 200, pr(), {}
        raise AssertionError(path)

    resolved = resolve_context_from_trigger(FakeApi(handler))
    assert resolved is not None
    assert resolved.pr_number == 609
    assert resolved.event_action == "synchronize"
    assert resolved.event_head_sha == "new"


def test_workflow_run_empty_metadata_recovers_pr_from_commit(monkeypatch) -> None:
    _set_env(monkeypatch)

    def handler(method: str, path: str):
        assert method == "GET"
        if path.endswith("/actions/runs/700"):
            return 200, trigger_run(pulls=[], sha="merge-ish"), {}
        if path.endswith("/commits/merge-ish/pulls"):
            return 200, [{"number": 609}], {}
        if path.endswith("/pulls/609"):
            return 200, pr(), {}
        raise AssertionError(path)

    resolved = resolve_context_from_trigger(FakeApi(handler))
    assert resolved is not None
    assert resolved.pr_number == 609
    assert resolved.event_before_sha == "merge-ish"


def test_fork_trigger_is_skipped_before_privileged_mutation(monkeypatch) -> None:
    _set_env(monkeypatch)

    def handler(method: str, path: str):
        assert method == "GET"
        assert path.endswith("/actions/runs/700")
        return 200, trigger_run(head_repo="someone/fork", pulls=[{"number": 609}]), {}

    assert resolve_context_from_trigger(FakeApi(handler)) is None


def test_unexpected_source_workflow_fails_closed(monkeypatch) -> None:
    _set_env(monkeypatch)
    bad = trigger_run(pulls=[{"number": 609}])
    bad["path"] = ".github/workflows/not-the-signal.yml"

    def handler(method: str, path: str):
        return 200, bad, {}

    try:
        resolve_context_from_trigger(FakeApi(handler))
    except RuntimeError as exc:
        assert "lifecycle signal" in str(exc)
    else:
        raise AssertionError("unexpected workflow source must fail closed")


def test_empty_pull_requests_matches_dynamic_run_via_commit_association() -> None:
    def handler(method: str, path: str):
        assert method == "GET"
        assert path.endswith("/commits/older/pulls")
        return 200, [{"number": 609}], {}

    api = FakeApi(handler)
    assert belongs_to_pr(
        api,
        run(2, "older", event="dynamic"),
        context=context(event_before_sha=""),
        pr=pr(),
        known_pr_shas={"new"},
        commit_link_cache={},
    )


def test_default_branch_is_never_cleanup_target_even_with_explicit_link() -> None:
    assert not belongs_to_pr(
        FakeApi(no_network),
        run(3, "new", branch="main", pulls=[{"number": 609}]),
        context=context(),
        pr=pr(),
        known_pr_shas={"new"},
        commit_link_cache={},
    )


def _drain_handler(state: str, queued_runs: list[dict]):
    def handler(method: str, path: str):
        if method == "GET" and path == f"/repos/{REPO}/pulls/609":
            return 200, pr(state=state), {}
        if method == "GET" and path.startswith(f"/repos/{REPO}/pulls/609/commits?"):
            return 200, [{"sha": "old"}, {"sha": "new"}], {}
        if method == "GET" and "/actions/runs?" in path:
            if "status=queued" in path:
                return 200, {"workflow_runs": queued_runs}, {}
            return 200, {"workflow_runs": []}, {}
        if method == "POST" and path.endswith("/cancel"):
            return 202, None, {}
        raise AssertionError(f"unexpected network call: {method} {path}")

    return handler


def test_open_pr_cancels_stale_head_and_preserves_current_head() -> None:
    api = FakeApi(_drain_handler("open", [run(10, "old"), run(11, "new")]))
    summary = drain(api, context())
    assert summary["inspected"] == 2
    assert summary["selected"] == 1
    assert summary["accepted"] == 1
    assert ("POST", f"/repos/{REPO}/actions/runs/10/cancel") in api.calls
    assert ("POST", f"/repos/{REPO}/actions/runs/11/cancel") not in api.calls


def test_closed_pr_cancels_current_and_stale_runs() -> None:
    api = FakeApi(
        _drain_handler("closed", [run(20, "old"), run(21, "new", event="dynamic")])
    )
    summary = drain(api, context(event_action="closed"))
    assert summary["selected"] == 2
    assert summary["accepted"] == 2


def test_live_pr_state_wins_after_reopen() -> None:
    api = FakeApi(_drain_handler("open", [run(30, "old"), run(31, "new")]))
    summary = drain(api, context(event_action="closed"))
    assert summary["live_state"] == "open"
    assert summary["selected"] == 1
    assert ("POST", f"/repos/{REPO}/actions/runs/31/cancel") not in api.calls


def test_cancel_transients_fall_back_to_force_cancel() -> None:
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
    assert cancel_run(api, REPO, 40) == CancelResult("forced", 202)
    assert cancel_attempts == 3
    assert api.sleeps == [1.0, 2.0]


def test_422_is_benign_only_after_completion() -> None:
    def handler(method: str, path: str):
        if method == "POST" and path.endswith("/cancel") and not path.endswith("/force-cancel"):
            return 422, {"message": "cannot cancel"}, {}
        if method == "GET" and path.endswith("/actions/runs/50"):
            return 200, {"status": "completed"}, {}
        raise AssertionError(f"unexpected network call: {method} {path}")

    api = FakeApi(handler)
    assert cancel_run(api, REPO, 50) == CancelResult("moved", 422)
    assert not any(path.endswith("/force-cancel") for _, path in api.calls)


def test_workflow_contract_has_no_pull_request_target() -> None:
    root = Path(__file__).resolve().parents[2]
    drain_workflow = (root / ".github/workflows/pr-obsolete-run-drain.yml").read_text(
        encoding="utf-8"
    )
    signal_workflow = (root / ".github/workflows/pr-lifecycle-signal.yml").read_text(
        encoding="utf-8"
    )
    assert "pull_request_target" not in drain_workflow
    assert "workflow_run:" in drain_workflow
    assert "pull_request:" in signal_workflow
    assert "permissions: {}" in signal_workflow
