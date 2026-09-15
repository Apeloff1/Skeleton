from __future__ import annotations

import pytest

from scripts.pr_obsolete_run_from_workflow_run import live_pr_head_converged


class FakeApi:
    def __init__(self, *, status: int = 200, payload: object) -> None:
        self.status = status
        self.payload = payload
        self.paths: list[str] = []

    def request(self, path: str):
        self.paths.append(path)
        return self.status, self.payload, {}


def test_open_pr_defers_drain_until_live_head_matches_signal() -> None:
    api = FakeApi(
        payload={
            "state": "open",
            "head": {"sha": "old-head"},
        }
    )

    assert not live_pr_head_converged(
        api,
        repo="Apeloff1/Skeleton",
        pr_number=681,
        signal_head_sha="new-head",
    )
    assert api.paths == ["/repos/Apeloff1/Skeleton/pulls/681"]


def test_open_pr_allows_drain_after_live_head_converges() -> None:
    api = FakeApi(
        payload={
            "state": "open",
            "head": {"sha": "new-head"},
        }
    )

    assert live_pr_head_converged(
        api,
        repo="Apeloff1/Skeleton",
        pr_number=681,
        signal_head_sha="new-head",
    )


def test_closed_pr_allows_drain_without_head_convergence() -> None:
    api = FakeApi(
        payload={
            "state": "closed",
            "head": {"sha": "older-head"},
        }
    )

    assert live_pr_head_converged(
        api,
        repo="Apeloff1/Skeleton",
        pr_number=681,
        signal_head_sha="new-head",
    )


def test_open_pr_missing_head_sha_fails_closed() -> None:
    api = FakeApi(payload={"state": "open", "head": {}})

    with pytest.raises(RuntimeError, match="missing head.sha"):
        live_pr_head_converged(
            api,
            repo="Apeloff1/Skeleton",
            pr_number=681,
            signal_head_sha="new-head",
        )


def test_refresh_failure_fails_closed() -> None:
    api = FakeApi(status=503, payload={})

    with pytest.raises(RuntimeError, match="HTTP 503"):
        live_pr_head_converged(
            api,
            repo="Apeloff1/Skeleton",
            pr_number=681,
            signal_head_sha="new-head",
        )
