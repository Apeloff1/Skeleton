from __future__ import annotations

import pytest

from scripts.pr_obsolete_run_from_workflow_run import (
    live_pr_head_converged,
    resolve_pr_number,
)


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
    head_ref: str = "feature/cleanup",
    state: str = "closed",
) -> dict[str, object]:
    return {
        "number": number,
        "state": state,
        "head": {
            "sha": sha,
            "ref": head_ref,
            "repo": {"full_name": "Apeloff1/Skeleton"},
        },
        "base": {"ref": "main"},
    }


def test_resolve_closed_unmerged_pr_from_exact_branch_and_sha_history() -> None:
    commit_path = "/repos/Apeloff1/Skeleton/commits/closed-head/pulls"
    history_path = (
        "/repos/Apeloff1/Skeleton/pulls?state=all&head="
        "Apeloff1%3Afeature%2Fcleanup&base=main&sort=updated&direction=desc&per_page=100"
    )
    api = ScriptedApi(
        {
            commit_path: (200, []),
            history_path: (
                200,
                [
                    _pr(867, sha="older-head"),
                    _pr(868, sha="closed-head"),
                ],
            ),
        }
    )

    assert (
        resolve_pr_number(
            api,
            repo="Apeloff1/Skeleton",
            hinted_number=0,
            head_sha="closed-head",
            head_ref="feature/cleanup",
            default_branch="main",
        )
        == 868
    )
    assert api.paths == [commit_path, history_path]


def test_branch_history_fallback_requires_immutable_signal_sha() -> None:
    commit_path = "/repos/Apeloff1/Skeleton/commits/missing-head/pulls"
    history_path = (
        "/repos/Apeloff1/Skeleton/pulls?state=all&head="
        "Apeloff1%3Afeature%2Fcleanup&base=main&sort=updated&direction=desc&per_page=100"
    )
    api = ScriptedApi(
        {
            commit_path: (200, []),
            history_path: (200, [_pr(868, sha="different-head")]),
        }
    )

    with pytest.raises(RuntimeError, match=r"branch_sha_matches=\[\]"):
        resolve_pr_number(
            api,
            repo="Apeloff1/Skeleton",
            hinted_number=0,
            head_sha="missing-head",
            head_ref="feature/cleanup",
            default_branch="main",
        )


def test_branch_history_ambiguity_fails_closed() -> None:
    commit_path = "/repos/Apeloff1/Skeleton/commits/shared-head/pulls"
    history_path = (
        "/repos/Apeloff1/Skeleton/pulls?state=all&head="
        "Apeloff1%3Afeature%2Fcleanup&base=main&sort=updated&direction=desc&per_page=100"
    )
    api = ScriptedApi(
        {
            commit_path: (200, []),
            history_path: (
                200,
                [
                    _pr(868, sha="shared-head"),
                    _pr(869, sha="shared-head"),
                ],
            ),
        }
    )

    with pytest.raises(RuntimeError, match=r"branch_sha_matches=\[868, 869\]"):
        resolve_pr_number(
            api,
            repo="Apeloff1/Skeleton",
            hinted_number=0,
            head_sha="shared-head",
            head_ref="feature/cleanup",
            default_branch="main",
        )
    assert api.paths == [commit_path, history_path]


def test_commit_association_ambiguity_fails_without_history_fallback() -> None:
    commit_path = "/repos/Apeloff1/Skeleton/commits/shared-head/pulls"
    api = ScriptedApi(
        {
            commit_path: (
                200,
                [
                    _pr(868, sha="shared-head"),
                    _pr(869, sha="shared-head"),
                ],
            )
        }
    )

    with pytest.raises(RuntimeError, match="multiple trusted PRs"):
        resolve_pr_number(
            api,
            repo="Apeloff1/Skeleton",
            hinted_number=0,
            head_sha="shared-head",
            head_ref="feature/cleanup",
            default_branch="main",
        )
    assert api.paths == [commit_path]


def test_open_pr_defers_until_rest_head_matches_signal() -> None:
    api = FakeApi(payload={"state": "open", "head": {"sha": "old-head"}})

    assert not live_pr_head_converged(
        api,
        repo="Apeloff1/Skeleton",
        pr_number=681,
        signal_head_sha="new-head",
    )
    assert api.paths == ["/repos/Apeloff1/Skeleton/pulls/681"]


def test_open_pr_allows_cleanup_after_rest_head_converges() -> None:
    api = FakeApi(payload={"state": "open", "head": {"sha": "new-head"}})

    assert live_pr_head_converged(
        api,
        repo="Apeloff1/Skeleton",
        pr_number=681,
        signal_head_sha="new-head",
    )


def test_closed_pr_allows_cleanup_without_head_match() -> None:
    api = FakeApi(payload={"state": "closed", "head": {"sha": "old-head"}})

    assert live_pr_head_converged(
        api,
        repo="Apeloff1/Skeleton",
        pr_number=681,
        signal_head_sha="new-head",
    )


def test_unknown_pr_state_fails_closed() -> None:
    api = FakeApi(payload={"state": "migrating", "head": {"sha": "new-head"}})

    with pytest.raises(RuntimeError, match="unknown state"):
        live_pr_head_converged(
            api,
            repo="Apeloff1/Skeleton",
            pr_number=681,
            signal_head_sha="new-head",
        )


def test_open_pr_without_head_sha_fails_closed() -> None:
    api = FakeApi(payload={"state": "open", "head": {}})

    with pytest.raises(RuntimeError, match="missing head.sha"):
        live_pr_head_converged(
            api,
            repo="Apeloff1/Skeleton",
            pr_number=681,
            signal_head_sha="new-head",
        )


def test_refresh_failure_fails_closed() -> None:
    api = FakeApi(payload={}, status=503)

    with pytest.raises(RuntimeError, match="HTTP 503"):
        live_pr_head_converged(
            api,
            repo="Apeloff1/Skeleton",
            pr_number=681,
            signal_head_sha="new-head",
        )
