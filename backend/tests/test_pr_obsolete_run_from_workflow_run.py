from __future__ import annotations

import os
import urllib.parse

import pytest

import scripts.pr_obsolete_run_from_workflow_run as adapter
from scripts.pr_obsolete_run_drain import COMMIT_PULLS_PAGE_SIZE, MAX_COMMIT_PULLS_PAGES
from scripts.pr_obsolete_run_from_workflow_run import (
    HISTORY_PAGE_SIZE,
    MAX_HISTORY_PAGES,
    canonical_commit_oid,
    live_pr_head_converged,
    parse_pr_hints_json,
    resolve_pr_numbers,
)


REPO = "Apeloff1/Skeleton"
HEAD_REF = "feature/cleanup"
HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"
CLOSED_SHA = "cccccccccccccccccccccccccccccccccccccccc"
SHARED_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class FakeApi:
    def __init__(self, *, payload: object, status: int = 200) -> None:
        self.payload = payload
        self.status = status
        self.paths: list[str] = []

    def request(self, path: str, *, method: str = "GET"):
        self.paths.append(path)
        return self.status, self.payload, {}


class ScriptedApi:
    def __init__(self, responses: dict[str, tuple[int, object]]) -> None:
        self.responses = responses
        self.paths: list[str] = []

    def request(self, path: str, *, method: str = "GET"):
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


def _commit_pulls_path(sha: str, page: int = 1) -> str:
    query = urllib.parse.urlencode({"per_page": COMMIT_PULLS_PAGE_SIZE, "page": page})
    quoted = urllib.parse.quote(sha, safe="")
    return f"/repos/{REPO}/commits/{quoted}/pulls?{query}"


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
    commit_path = _commit_pulls_path(CLOSED_SHA)
    api = ScriptedApi(
        {
            commit_path: (200, []),
            _history_path(): (
                200,
                [_pr(867, sha="older-head"), _pr(868, sha=CLOSED_SHA)],
            ),
        }
    )

    assert resolve_pr_numbers(
        api,
        repo=REPO,
        hinted_numbers=[],
        head_sha=CLOSED_SHA,
        head_ref=HEAD_REF,
        default_branch="main",
    ) == [868]
    assert api.paths == [commit_path, _history_path()]


def test_resolve_closed_unmerged_pr_from_second_history_page() -> None:
    commit_path = _commit_pulls_path(CLOSED_SHA)
    first_page = [
        _pr(number, sha=f"older-head-{number}")
        for number in range(1000, 1000 + HISTORY_PAGE_SIZE)
    ]
    api = ScriptedApi(
        {
            commit_path: (200, []),
            _history_path(1): (200, first_page),
            _history_path(2): (200, [_pr(868, sha=CLOSED_SHA)]),
        }
    )

    assert resolve_pr_numbers(
        api,
        repo=REPO,
        hinted_numbers=[],
        head_sha=CLOSED_SHA,
        head_ref=HEAD_REF,
        default_branch="main",
    ) == [868]
    assert api.paths == [commit_path, _history_path(1), _history_path(2)]


def test_zero_commit_and_history_match_is_benign_noop() -> None:
    commit_path = _commit_pulls_path(HEAD_SHA)
    api = ScriptedApi(
        {
            commit_path: (200, []),
            _history_path(): (200, [_pr(868, sha="other")]),
        }
    )

    assert resolve_pr_numbers(
        api,
        repo=REPO,
        hinted_numbers=[],
        head_sha=HEAD_SHA,
        head_ref=HEAD_REF,
        default_branch="main",
    ) == []
    assert api.paths == [commit_path, _history_path()]


def test_commit_association_keeps_every_trusted_pr_without_history_fallback() -> None:
    commit_path = _commit_pulls_path(SHARED_SHA)
    api = ScriptedApi(
        {
            commit_path: (
                200,
                [_pr(868, sha=SHARED_SHA), _pr(869, sha=SHARED_SHA)],
            )
        }
    )

    assert resolve_pr_numbers(
        api,
        repo=REPO,
        hinted_numbers=[],
        head_sha=SHARED_SHA,
        head_ref=HEAD_REF,
        default_branch="main",
    ) == [868, 869]
    assert api.paths == [commit_path]


def test_branch_history_keeps_every_exact_sha_match() -> None:
    commit_path = _commit_pulls_path(HEAD_SHA)
    api = ScriptedApi(
        {
            commit_path: (200, []),
            _history_path(): (
                200,
                [_pr(868, sha=HEAD_SHA), _pr(869, sha=HEAD_SHA)],
            ),
        }
    )

    assert resolve_pr_numbers(
        api,
        repo=REPO,
        hinted_numbers=[],
        head_sha=HEAD_SHA,
        head_ref=HEAD_REF,
        default_branch="main",
    ) == [868, 869]


def test_hints_union_commit_association() -> None:
    commit_path = _commit_pulls_path(HEAD_SHA)
    api = ScriptedApi(
        {
            f"/repos/{REPO}/pulls/868": (200, _pr(868, sha=HEAD_SHA)),
            commit_path: (200, [_pr(869, sha=HEAD_SHA)]),
        }
    )

    assert resolve_pr_numbers(
        api,
        repo=REPO,
        hinted_numbers=[868],
        head_sha=HEAD_SHA,
        head_ref=HEAD_REF,
        default_branch="main",
    ) == [868, 869]
    assert api.paths == [f"/repos/{REPO}/pulls/868", commit_path]


def test_commit_association_recovers_later_page_matches() -> None:
    first_page = [_pr(number, sha=HEAD_SHA) for number in range(2000, 2000 + COMMIT_PULLS_PAGE_SIZE)]
    api = ScriptedApi(
        {
            _commit_pulls_path(HEAD_SHA, 1): (200, first_page),
            _commit_pulls_path(HEAD_SHA, 2): (200, [_pr(868, sha=HEAD_SHA)]),
        }
    )

    assert resolve_pr_numbers(
        api,
        repo=REPO,
        hinted_numbers=[],
        head_sha=HEAD_SHA,
        head_ref=HEAD_REF,
        default_branch="main",
    ) == [*range(2000, 2000 + COMMIT_PULLS_PAGE_SIZE), 868]


def test_commit_association_scan_bound_fails_closed() -> None:
    full_page = [
        _pr(number, sha=HEAD_SHA)
        for number in range(3000, 3000 + COMMIT_PULLS_PAGE_SIZE)
    ]
    responses = {
        _commit_pulls_path(HEAD_SHA, page): (200, full_page)
        for page in range(1, MAX_COMMIT_PULLS_PAGES + 1)
    }
    api = ScriptedApi(responses)

    with pytest.raises(RuntimeError, match="bounded identity scan"):
        resolve_pr_numbers(
            api,
            repo=REPO,
            hinted_numbers=[],
            head_sha=HEAD_SHA,
            head_ref=HEAD_REF,
            default_branch="main",
        )


def test_history_api_failure_fails_closed() -> None:
    commit_path = _commit_pulls_path(HEAD_SHA)
    api = ScriptedApi(
        {
            commit_path: (200, []),
            _history_path(): (503, {}),
        }
    )

    with pytest.raises(RuntimeError, match="branch history: HTTP 503"):
        resolve_pr_numbers(
            api,
            repo=REPO,
            hinted_numbers=[],
            head_sha=HEAD_SHA,
            head_ref=HEAD_REF,
            default_branch="main",
        )


def test_history_scan_bound_fails_closed_instead_of_silently_truncating() -> None:
    commit_path = _commit_pulls_path(HEAD_SHA)
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
        resolve_pr_numbers(
            api,
            repo=REPO,
            hinted_numbers=[],
            head_sha=HEAD_SHA,
            head_ref=HEAD_REF,
            default_branch="main",
        )


def test_mismatched_hint_does_not_block_sha_recovery() -> None:
    commit_path = _commit_pulls_path(HEAD_SHA)
    api = ScriptedApi(
        {
            f"/repos/{REPO}/pulls/681": (
                200,
                {
                    "number": 681,
                    "head": {"ref": "other", "repo": {"full_name": REPO}, "sha": HEAD_SHA},
                    "base": {"ref": "main"},
                },
            ),
            commit_path: (200, [_pr(868, sha=HEAD_SHA)]),
        }
    )

    assert resolve_pr_numbers(
        api,
        repo=REPO,
        hinted_numbers=[681],
        head_sha=HEAD_SHA,
        head_ref=HEAD_REF,
        default_branch="main",
    ) == [868]


def test_hinted_pr_fetch_failure_fails_closed() -> None:
    api = ScriptedApi({f"/repos/{REPO}/pulls/681": (503, {})})
    with pytest.raises(RuntimeError, match="hinted PR #681: HTTP 503"):
        resolve_pr_numbers(
            api,
            repo=REPO,
            hinted_numbers=[681],
            head_sha=HEAD_SHA,
            head_ref=HEAD_REF,
            default_branch="main",
        )


def test_main_skips_no_target_without_calling_privileged_drainer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commit_path = _commit_pulls_path(HEAD_SHA)
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
        "WORKFLOW_RUN_PR_HINTS": "[]",
    }.items():
        monkeypatch.setenv(key, value)

    assert adapter.main() == 0
    assert api.paths == [commit_path, _history_path()]


def test_main_drains_every_trusted_completion_pr(monkeypatch: pytest.MonkeyPatch) -> None:
    commit_path = _commit_pulls_path(HEAD_SHA)
    api = ScriptedApi(
        {
            f"/repos/{REPO}/pulls/868": (200, _pr(868, sha=HEAD_SHA)),
            f"/repos/{REPO}/pulls/869": (200, _pr(869, sha=HEAD_SHA)),
            commit_path: (200, [_pr(868, sha=HEAD_SHA), _pr(869, sha=HEAD_SHA)]),
        }
    )
    monkeypatch.setattr(adapter, "GitHubApi", lambda _token: api)
    drained: list[str] = []

    def record_drain() -> int:
        drained.append(os.environ["PR_NUMBER"])
        return 0

    monkeypatch.setattr(adapter, "drain_main", record_drain)
    for key, value in {
        "GH_TOKEN": "test-token",
        "REPO": REPO,
        "EVENT_HEAD_REPO": REPO,
        "EVENT_HEAD_REF": HEAD_REF,
        "EVENT_HEAD_SHA": HEAD_SHA,
        "DEFAULT_BRANCH": "main",
        "WORKFLOW_RUN_PR_HINTS": "[868, 869]",
    }.items():
        monkeypatch.setenv(key, value)

    assert adapter.main() == 0
    assert drained == ["868", "869"]


def test_main_malformed_hint_json_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        adapter,
        "GitHubApi",
        lambda _token: (_ for _ in ()).throw(AssertionError("api")),
    )
    monkeypatch.setattr(
        adapter,
        "drain_main",
        lambda: (_ for _ in ()).throw(AssertionError("drain")),
    )
    for key, value in {
        "GH_TOKEN": "test-token",
        "REPO": REPO,
        "EVENT_HEAD_REPO": REPO,
        "EVENT_HEAD_REF": HEAD_REF,
        "EVENT_HEAD_SHA": HEAD_SHA,
        "DEFAULT_BRANCH": "main",
        "WORKFLOW_RUN_PR_HINTS": '{"number": 11}',
    }.items():
        monkeypatch.setenv(key, value)

    assert adapter.main() == 1


def test_parse_pr_hints_json_fails_closed_on_object_payload() -> None:
    with pytest.raises(RuntimeError, match="JSON array"):
        parse_pr_hints_json('{"number": 11}')


def test_uppercase_head_sha_is_canonicalized_before_lookup() -> None:
    commit_path = _commit_pulls_path(HEAD_SHA)
    api = ScriptedApi(
        {
            commit_path: (200, [_pr(868, sha=HEAD_SHA)]),
        }
    )

    assert resolve_pr_numbers(
        api,
        repo=REPO,
        hinted_numbers=[],
        head_sha=HEAD_SHA.upper(),
        head_ref=HEAD_REF,
        default_branch="main",
    ) == [868]
    assert api.paths == [commit_path]
    assert canonical_commit_oid(HEAD_SHA.upper()) == HEAD_SHA


def test_branch_history_matches_head_sha_case_insensitively() -> None:
    commit_path = _commit_pulls_path(HEAD_SHA)
    api = ScriptedApi(
        {
            commit_path: (200, []),
            _history_path(): (200, [_pr(868, sha=HEAD_SHA.upper())]),
        }
    )

    assert resolve_pr_numbers(
        api,
        repo=REPO,
        hinted_numbers=[],
        head_sha=HEAD_SHA,
        head_ref=HEAD_REF,
        default_branch="main",
    ) == [868]


@pytest.mark.parametrize(
    "head_sha",
    [
        HEAD_SHA[:-1],
        HEAD_SHA + "a",
        HEAD_SHA[:7],
        f" {HEAD_SHA}",
        f"{HEAD_SHA} ",
        f"\t{HEAD_SHA}",
        "g" * 40,
        "0" * 39 + "z",
    ],
)
def test_malformed_head_sha_fails_closed_before_api_lookup(head_sha: str) -> None:
    api = FakeApi(payload=[], status=200)
    with pytest.raises(RuntimeError, match="40-character hex commit OID"):
        resolve_pr_numbers(
            api,
            repo=REPO,
            hinted_numbers=[],
            head_sha=head_sha,
            head_ref=HEAD_REF,
            default_branch="main",
        )
    assert api.paths == []


def test_main_malformed_head_sha_fails_closed_before_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        adapter,
        "GitHubApi",
        lambda _token: (_ for _ in ()).throw(AssertionError("api")),
    )
    monkeypatch.setattr(
        adapter,
        "drain_main",
        lambda: (_ for _ in ()).throw(AssertionError("drain")),
    )
    for key, value in {
        "GH_TOKEN": "test-token",
        "REPO": REPO,
        "EVENT_HEAD_REPO": REPO,
        "EVENT_HEAD_REF": HEAD_REF,
        "EVENT_HEAD_SHA": "abc123",
        "DEFAULT_BRANCH": "main",
        "WORKFLOW_RUN_PR_HINTS": "[]",
    }.items():
        monkeypatch.setenv(key, value)

    assert adapter.main() == 1


def test_main_writes_canonical_head_sha_before_privileged_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commit_path = _commit_pulls_path(HEAD_SHA)
    api = ScriptedApi(
        {
            f"/repos/{REPO}/pulls/868": (200, _pr(868, sha=HEAD_SHA)),
            commit_path: (200, [_pr(868, sha=HEAD_SHA)]),
        }
    )
    monkeypatch.setattr(adapter, "GitHubApi", lambda _token: api)
    seen: list[str] = []

    def record_drain() -> int:
        seen.append(os.environ["EVENT_HEAD_SHA"])
        return 0

    monkeypatch.setattr(adapter, "drain_main", record_drain)
    for key, value in {
        "GH_TOKEN": "test-token",
        "REPO": REPO,
        "EVENT_HEAD_REPO": REPO,
        "EVENT_HEAD_REF": HEAD_REF,
        "EVENT_HEAD_SHA": HEAD_SHA.upper(),
        "DEFAULT_BRANCH": "main",
        "WORKFLOW_RUN_PR_HINTS": "[868]",
    }.items():
        monkeypatch.setenv(key, value)

    assert adapter.main() == 0
    assert seen == [HEAD_SHA]
    assert os.environ["EVENT_HEAD_SHA"] == HEAD_SHA


def test_open_pr_defers_until_rest_head_matches_signal() -> None:
    api = FakeApi(payload={"state": "open", "head": {"sha": CLOSED_SHA}})
    assert not live_pr_head_converged(
        api,
        repo=REPO,
        pr_number=681,
        signal_head_sha=HEAD_SHA,
    )
    assert api.paths == [f"/repos/{REPO}/pulls/681"]


def test_open_pr_allows_cleanup_after_rest_head_converges() -> None:
    api = FakeApi(payload={"state": "open", "head": {"sha": HEAD_SHA}})
    assert live_pr_head_converged(
        api,
        repo=REPO,
        pr_number=681,
        signal_head_sha=HEAD_SHA,
    )


def test_open_pr_malformed_live_sha_fails_closed() -> None:
    api = FakeApi(payload={"state": "open", "head": {"sha": "abc123"}})
    with pytest.raises(RuntimeError, match="40-character hex commit OID"):
        live_pr_head_converged(
            api,
            repo=REPO,
            pr_number=681,
            signal_head_sha=HEAD_SHA,
        )


def test_open_pr_head_match_is_case_insensitive() -> None:
    api = FakeApi(payload={"state": "open", "head": {"sha": HEAD_SHA.upper()}})
    assert live_pr_head_converged(
        api,
        repo=REPO,
        pr_number=681,
        signal_head_sha=HEAD_SHA,
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
