from __future__ import annotations

import pytest

from scripts.pr_obsolete_run_drain import (
    COMMIT_PULLS_PAGE_SIZE,
    PR_COMMITS_PAGE_SIZE,
    RUN_PAGE_SIZE,
    CancelResult,
    DrainContext,
    belongs_to_pr,
    build_context_from_env,
    cancel_run,
    commit_links_pr,
    drain,
    list_commit_associated_pulls,
    list_pr_commit_shas,
    list_runs,
)

REPO = "Apeloff1/Skeleton"
OLDER_SHA = "cccccccccccccccccccccccccccccccccccccccc"
HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"
BEFORE_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


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
        "event_head_sha": HEAD_SHA,
        "event_before_sha": BEFORE_SHA,
        "default_branch": "main",
    }
    values.update(overrides)
    return DrainContext(**values)


def pr(state: str = "open", sha: str = HEAD_SHA) -> dict:
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
        run(1, BEFORE_SHA),
        context=context(),
        pr=pr(),
        known_pr_shas={HEAD_SHA},
        commit_link_cache={},
    )


def test_empty_pull_requests_matches_dynamic_run_via_commit_association() -> None:
    def handler(method: str, path: str):
        assert method == "GET"
        assert path.endswith(f"/commits/{OLDER_SHA}/pulls") or f"/commits/{OLDER_SHA}/pulls?" in path
        return 200, [{"number": 556}], {}

    api = FakeApi(handler)
    assert belongs_to_pr(
        api,
        run(2, OLDER_SHA, event="dynamic"),
        context=context(event_before_sha=""),
        pr=pr(),
        known_pr_shas={HEAD_SHA},
        commit_link_cache={},
    )


def test_default_branch_is_never_a_pr_cleanup_target_even_with_explicit_link() -> None:
    api = FakeApi(no_network)
    assert not belongs_to_pr(
        api,
        run(3, HEAD_SHA, branch="main", pulls=[{"number": 556}]),
        context=context(),
        pr=pr(),
        known_pr_shas={HEAD_SHA},
        commit_link_cache={},
    )


def test_fallback_requires_same_repository() -> None:
    api = FakeApi(no_network)
    assert not belongs_to_pr(
        api,
        run(4, BEFORE_SHA, head_repo="someone/fork"),
        context=context(),
        pr=pr(),
        known_pr_shas={BEFORE_SHA, HEAD_SHA},
        commit_link_cache={},
    )


def _drain_handler(state: str, queued_runs: list[dict]):
    def handler(method: str, path: str):
        if method == "GET" and path == f"/repos/{REPO}/pulls/556":
            return 200, pr(state=state), {}
        if method == "GET" and path.startswith(f"/repos/{REPO}/pulls/556/commits?"):
            return 200, [{"sha": BEFORE_SHA}, {"sha": HEAD_SHA}], {}
        if method == "GET" and "/actions/runs?" in path:
            if "status=queued" in path:
                return 200, {"workflow_runs": queued_runs}, {}
            return 200, {"workflow_runs": []}, {}
        if method == "POST" and path.endswith("/cancel"):
            return 202, None, {}
        raise AssertionError(f"unexpected network call: {method} {path}")

    return handler


def test_synchronize_cancels_stale_head_and_preserves_current_head() -> None:
    api = FakeApi(_drain_handler("open", [run(10, BEFORE_SHA), run(11, HEAD_SHA)]))
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
            [run(20, BEFORE_SHA), run(21, HEAD_SHA, event="dynamic")],
        )
    )
    summary = drain(api, context(event_action="closed"))
    assert summary["selected"] == 2
    assert summary["accepted"] == 2


def test_live_pr_state_wins_over_stale_closed_event_after_reopen() -> None:
    api = FakeApi(_drain_handler("open", [run(30, BEFORE_SHA), run(31, HEAD_SHA)]))
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


def test_commit_association_recovers_pr_from_later_page() -> None:
    def handler(method: str, path: str):
        assert method == "GET"
        if path.endswith("page=1"):
            return 200, [{"number": n} for n in range(1, COMMIT_PULLS_PAGE_SIZE + 1)], {}
        if path.endswith("page=2"):
            return 200, [{"number": 556}], {}
        raise AssertionError(path)

    assert commit_links_pr(FakeApi(handler), REPO, OLDER_SHA, 556, {})


def test_commit_association_scan_bound_fails_closed() -> None:
    def handler(method: str, path: str):
        return 200, [{"number": n} for n in range(1, COMMIT_PULLS_PAGE_SIZE + 1)], {}

    with pytest.raises(RuntimeError, match="bounded identity scan"):
        commit_links_pr(FakeApi(handler), REPO, OLDER_SHA, 556, {})


@pytest.mark.parametrize(
    "sha",
    [
        OLDER_SHA[:-1],
        OLDER_SHA + "a",
        OLDER_SHA[:7],
        f" {OLDER_SHA}",
        f"{OLDER_SHA} ",
        "g" * 40,
    ],
)
def test_commit_association_rejects_malformed_sha_before_api_lookup(sha: str) -> None:
    api = FakeApi(no_network)
    with pytest.raises(RuntimeError, match="40-character hex commit OID"):
        list_commit_associated_pulls(api, REPO, sha)
    assert api.calls == []


def test_commit_association_canonicalizes_uppercase_sha_before_lookup() -> None:
    def handler(method: str, path: str):
        assert method == "GET"
        assert f"/commits/{OLDER_SHA}/pulls" in path
        assert OLDER_SHA.upper() not in path
        return 200, [{"number": 556}], {}

    pulls = list_commit_associated_pulls(FakeApi(handler), REPO, OLDER_SHA.upper())
    assert pulls == [{"number": 556}]


def test_live_run_listing_scan_bound_fails_closed() -> None:
    def handler(method: str, path: str):
        assert method == "GET"
        assert "/actions/runs?" in path
        return 200, {"workflow_runs": [{"id": n} for n in range(RUN_PAGE_SIZE)]}, {}

    with pytest.raises(RuntimeError, match="bounded identity scan"):
        list_runs(FakeApi(handler), REPO, "queued")


def test_pr_commit_listing_scan_bound_fails_closed() -> None:
    def handler(method: str, path: str):
        assert method == "GET"
        assert "/pulls/556/commits?" in path
        return 200, [{"sha": f"{n:040x}"} for n in range(PR_COMMITS_PAGE_SIZE)], {}

    with pytest.raises(RuntimeError, match="bounded identity scan"):
        list_pr_commit_shas(FakeApi(handler), REPO, 556)


def _context_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    values = {
        "REPO": REPO,
        "CURRENT_RUN_ID": "999",
        "PR_NUMBER": "556",
        "PR_ACTION": "synchronize",
        "EVENT_HEAD_REPO": REPO,
        "EVENT_HEAD_REF": "feature/drain",
        "EVENT_HEAD_SHA": HEAD_SHA,
        "EVENT_BEFORE_SHA": "",
        "DEFAULT_BRANCH": "main",
    }
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_build_context_from_env_canonicalizes_event_shas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _context_env(
        monkeypatch,
        EVENT_HEAD_SHA=HEAD_SHA.upper(),
        EVENT_BEFORE_SHA=BEFORE_SHA.upper(),
    )
    context = build_context_from_env()
    assert context.event_head_sha == HEAD_SHA
    assert context.event_before_sha == BEFORE_SHA


def test_build_context_from_env_rejects_malformed_head_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _context_env(monkeypatch, EVENT_HEAD_SHA="abc123")
    with pytest.raises(RuntimeError, match="40-character hex commit OID"):
        build_context_from_env()


def test_build_context_from_env_rejects_malformed_before_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _context_env(monkeypatch, EVENT_BEFORE_SHA="old")
    with pytest.raises(RuntimeError, match="40-character hex commit OID"):
        build_context_from_env()


def test_commit_association_http_error_fails_closed() -> None:
    def handler(method: str, path: str):
        assert method == "GET"
        assert f"/commits/{OLDER_SHA}/pulls" in path
        return 500, None, {}

    cache: dict[str, bool] = {}
    with pytest.raises(RuntimeError, match="failed to resolve PR associations"):
        commit_links_pr(FakeApi(handler), REPO, OLDER_SHA, 556, cache)
    assert cache == {}


def test_commit_links_pr_malformed_sha_does_not_hit_api() -> None:
    api = FakeApi(no_network)
    assert commit_links_pr(api, REPO, "abc123", 556, {}) is False
    assert api.calls == []


def test_list_pr_commit_shas_canonicalizes_uppercase() -> None:
    def handler(method: str, path: str):
        assert method == "GET"
        assert path.startswith(f"/repos/{REPO}/pulls/556/commits?")
        return 200, [{"sha": HEAD_SHA.upper()}, {"sha": BEFORE_SHA}], {}

    assert list_pr_commit_shas(FakeApi(handler), REPO, 556) == {HEAD_SHA, BEFORE_SHA}


def test_list_pr_commit_shas_rejects_malformed_oid() -> None:
    def handler(method: str, path: str):
        return 200, [{"sha": "not-an-oid"}], {}

    with pytest.raises(RuntimeError, match="40-character hex commit OID"):
        list_pr_commit_shas(FakeApi(handler), REPO, 556)


def test_open_pr_malformed_live_head_fails_closed() -> None:
    def handler(method: str, path: str):
        if method == "GET" and path == f"/repos/{REPO}/pulls/556":
            return 200, pr(sha="abc123"), {}
        raise AssertionError(f"unexpected network call: {method} {path}")

    with pytest.raises(RuntimeError, match="40-character hex commit OID"):
        drain(FakeApi(handler), context())


def test_malformed_run_sha_is_not_attributed_without_explicit_pr_link() -> None:
    api = FakeApi(no_network)
    assert not belongs_to_pr(
        api,
        run(99, "abc123"),
        context=context(),
        pr=pr(),
        known_pr_shas={HEAD_SHA},
        commit_link_cache={},
    )
