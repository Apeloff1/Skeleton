from __future__ import annotations

import pytest

from scripts.pr_obsolete_run_from_workflow_run import live_pr_head_converged


class FakeApi:
    def __init__(self, *, payload: object, status: int = 200) -> None:
        self.payload = payload
        self.status = status
        self.paths: list[str] = []

    def request(self, path: str):
        self.paths.append(path)
        return self.status, self.payload, {}


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
