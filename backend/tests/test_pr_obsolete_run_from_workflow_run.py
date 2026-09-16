from __future__ import annotations

import urllib.parse

import pytest

import scripts.pr_obsolete_run_from_workflow_run as adapter
from scripts.pr_obsolete_run_from_workflow_run import (
    HISTORY_PAGE_SIZE,
    MAX_HISTORY_PAGES,
    live_pr_head_converged,
    resolve_pr_number,
)


REPO = "Apeloff1/Skeleton"
HEAD_REF = "feature/cleanup"
HEAD_SHA = "head-sha"


class FakeApi:
    def __init__(self, *, payload: object, status: int = 200) -> None:
        self.payload = payload
        self.status = status
        self.paths: list[str] = []

    def request(self, path: str):
        self.paths.append(path)
        return self.status, self.payload, {}


class ScriptedApi:
    def __init__(self, responses: dict[str, tuple[int, object]]) -> None:
        self.responses = responses
        self.paths: list[str] = []

    def request(self, path: str):
        self.paths.append(path)
        status, payload = self.responses[path]
        return status, payload, {}


def _pr(
    number: int,
    *,
    sha: str,
    head_ref: str = HEAD_REF,
    state: str = "closed",
) -> dict[str, object]:
    return {
        "number": number,
        "state": state,
        "head": {
            "sha": sha,
            "ref": head_ref,
            "repo": {"full_name": REPO},
        },
        "base": {"ref": "main"},
    }


def _history_path(page: int = 1) -> str:
    query = urllib.parse.urlencode(
        {
            "state": "all",
            "head": "Apeloff1:feature/cleanup",
            "base": "main",
            "sort": "updated",
            "direction": "desc",
            "per_page": HISTORY_PAGE_SIZE,
            "page": page,
        }
    )
    return f"/repos/{REPO}/pulls?{query}"


def test_resolve_closed_unmerged_pr_from_exact_branch_and_sha_history() -> None:
    commit_path = f"/repos/{REPO}/commits/closed-head/pulls"
    api = ScriptedApi(
        {
            commit_path: (200, []),
            _history_path(): (
                200,
                [_pr(867, sha="older-head"), _pr(868, sha="closed-head")],
            ),
        }
    )

    assert (
        resolve_pr_number(
            api,
            repo=REPO,
            hinted_number=0,
            head_sha="closed-head",
            head_ref=HEAD_REF,
            default_branch="main",
        )
        == 868
    )
    assert api.paths == [commit_path, _history_path()]


def test_resolve_closed_unmerged_pr_from_second_history_page() -> None:
    commit_path = f"/repos/{REPO}/commits/closed-head/pulls"
    first_page = [
        _pr(number, sha=f"older-head-{number}")
        for number in range(1000, 1000 + HISTORY_PAGE_SIZE)
    ]
    api = ScriptedApi(
        {
            commit_path: (200, []),
            _history_path(1): (200, first_page),
            _history_path(2): (200, [_pr(868, sha="closed-head")]),
        }
    )

    assert (
        resolve_pr_number(
            api,
            repo=REPO,
            hinted_number=0,
            head_sha="closed-head",
            head_ref=HEAD_REF,
            default_branch="main",
        )
        == 868
    )
    assert api.paths == [commit_path, _history_path(1), _history_path(2)]


def test_zero_commit_and_history_match_is_benign_noop() -> None:
    commit_path = f"/repos/{REPO}/commits/{HEAD_SHA}/pulls"
    api = ScriptedApi(
        {
            commit_path: (200, []),
            _history_path(): (200, [_pr(868, sha="other")]),
        }
    )

    assert (
        resolve_pr_number(
            api,
            repo=REPO,
            hinted_number=0,
            head_sha=HEAD_SHA,
            head_ref=HEAD_REF,
            default_branch="main",
        )
        is None
    )
    assert api.paths == [commit_path, _history_path()]


def test_commit_association_ambiguity_fails_without_history_fallback() -> None:
    commit_path = f"/repos/{REPO}/commits/shared-head/pulls"
    api = ScriptedApi(
        {
            commit_path: (
                200,
                [_pr(868, sha="shared-head"), _pr(869, sha="shared-head")],
            )
        }
    )

    with pytest.raises(RuntimeError, match="multiple trusted PRs"):
        resolve_pr_number(
            api,
            repo=REPO,
            hinted_number=0,
            head_sha="shared-head",
            head_ref=HEAD_REF,
            default_branch="main",
        )
    assert api.paths == [commit_path]


def test_branch_history_ambiguity_fails_closed() -> None:
    commit_path = f"/repos/{REPO}/commits/{HEAD_SHA}/pulls"
    api = ScriptedApi(
        {
            commit_path: (200, []),
            _history_path(): (
                200,
                [_pr(868, sha=HEAD_SHA), _pr(869, sha=HEAD_SHA)],
            ),
        }
    )

    with pytest.raises(RuntimeError, match="branch history"):
        resolve_pr_number(
            api,
            repo=REPO,
            hinted_number=0,
            head_sha=HEAD_SHA,
            head_ref=HEAD_REF,
            default_branch="main",
        )


def test_history_api_failure_fails_closed() -> None:
    commit_path = f"/repos/{REPO}/commits/{HEAD_SHA}/pulls"
    api = ScriptedApi(
        {
            commit_path: (200, []),
            _history_path(): (503, {}),
        }
    )

    with pytest.raises(RuntimeError, match="branch history: HTTP 503"):
        resolve_pr_number(
            api,
            repo=REPO,
            hinted_number=0,
            head_sha=HEAD_SHA,
            head_ref=HEAD_REF,
            default_branch="main",
        )


def test_history_scan_bound_fails_closed_instead_of_silently_truncating() -> None:
    commit_path = f"/repos/{REPO}/commits/{HEAD_SHA}/pulls"
    full_page = [
        _pr(number, sha=f"other-{number}")
        for number in range(2000, 2000 + HISTORY_PAGE_SIZE)
    ]
    responses: dict[str, tuple[int, object]] = {commit_path: (200, [])}
    responses.update(
        {
            _history_path(page): (200, full_page)
            for page in range(1, MAX_HISTORY_PAGES + 1)
        }
    )
    api = ScriptedApi(responses)

    with pytest.raises(RuntimeError, match="bounded 1000-entry identity scan"):
        resolve_pr_number(
            api,
            repo=REPO,
            hinted_number=0,
            head_sha=HEAD_SHA,
            head_ref=HEAD_REF,
            default_branch="main",
        )


def test_hinted_pr_identity_mismatch_still_fails_closed() -> None:
    api = FakeApi(
        payload={
            "number": 681,
            "head": {"ref": "other", "repo": {"full_name": REPO}},
            "base": {"ref": "main"},
        }
    )
    with pytest.raises(RuntimeError, match="hint failed"):
        resolve_pr_number(
            api,
            repo=REPO,
            hinted_number=681,
            head_sha=HEAD_SHA,
            head_ref=HEAD_REF,
            default_branch="main",
        )


def test_main_skips_no_target_without_calling_privileged_drainer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commit_path = f"/repos/{REPO}/commits/{HEAD_SHA}/pulls"
    api = ScriptedApi(
        {
            commit_path: (200, []),
            _history_path(): (200, []),
        }
    )
    monkeypatch.setattr(adapter, "GitHubApi", lambda _token: api)

    def unexpected_drain() -> int:
        raise AssertionError("privileged drainer must not run without a trusted PR")

    monkeypatch.setattr(adapter, "drain_main", unexpected_drain)
    for key, value in {
        "GH_TOKEN": "test-token",
        "REPO": REPO,
        "EVENT_HEAD_REPO": REPO,
        "EVENT_HEAD_REF": HEAD_REF,
        "EVENT_HEAD_SHA": HEAD_SHA,
        "DEFAULT_BRANCH": "main",
        "PR_NUMBER": "",
    }.items():
        monkeypatch.setenv(key, value)

    assert adapter.main() == 0
    assert api.paths == [commit_path, _history_path()]


def test_open_pr_defers_until_rest_head_matches_signal() -> None:
    api = FakeApi(payload={"state": "open", "head": {"sha": "old-head"}})
    assert not live_pr_head_converged(
        api,
        repo=REPO,
        pr_number=681,
        signal_head_sha="new-head",
    )
    assert api.paths == [f"/repos/{REPO}/pulls/681"]


def test_open_pr_allows_cleanup_after_rest_head_converges() -> None:
    api = FakeApi(payload={"state": "open", "head": {"sha": "new-head"}})
    assert live_pr_head_converged(
        api,
        repo=REPO,
        pr_number=681,
        signal_head_sha="new-head",
    )


def test_closed_pr_allows_cleanup_without_head_match() -> None:
    api = FakeApi(payload={"state": "closed", "head": {"sha": "old-head"}})
    assert live_pr_head_converged(
        api,
        repo=REPO,
        pr_number=681,
        signal_head_sha="new-head",
    )


def test_unknown_pr_state_fails_closed() -> None:
    api = FakeApi(payload={"state": "migrating", "head": {"sha": "new-head"}})
    with pytest.raises(RuntimeError, match="unknown state"):
        live_pr_head_converged(
            api,
            repo=REPO,
            pr_number=681,
            signal_head_sha="new-head",
        )


def test_open_pr_without_head_sha_fails_closed() -> None:
    api = FakeApi(payload={"state": "open", "head": {}})
    with pytest.raises(RuntimeError, match="missing head.sha"):
        live_pr_head_converged(
            api,
            repo=REPO,
            pr_number=681,
            signal_head_sha="new-head",
        )


def test_refresh_failure_fails_closed() -> None:
    api = FakeApi(payload={}, status=503)
    with pytest.raises(RuntimeError, match="HTTP 503"):
        live_pr_head_converged(
            api,
            repo=REPO,
            pr_number=681,
            signal_head_sha="new-head",
        )
