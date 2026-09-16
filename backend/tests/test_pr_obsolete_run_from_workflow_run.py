from __future__ import annotations

import pytest

import scripts.pr_obsolete_run_from_workflow_run as adapter
from scripts.pr_obsolete_run_from_workflow_run import (
    live_pr_head_converged,
    resolve_pr_number,
)


REPO = "Apeloff1/Skeleton"
HEAD_REF = "fix/cors-policy-current-main-v3"
HEAD_SHA = "head-sha"


class FakeApi:
    def __init__(self, *, payload: object, status: int = 200) -> None:
        self.payload = payload
        self.status = status
        self.paths: list[str] = []

    def request(self, path: str):
        self.paths.append(path)
        return self.status, self.payload, {}


def candidate(
    number: int,
    *,
    head_ref: str = HEAD_REF,
    base_ref: str = "main",
    repo: str = REPO,
) -> dict:
    return {
        "number": number,
        "head": {"ref": head_ref, "repo": {"full_name": repo}},
        "base": {"ref": base_ref},
    }


def test_unhinted_signal_without_trusted_pr_is_benign_noop() -> None:
    api = FakeApi(payload=[])

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
    assert api.paths == [f"/repos/{REPO}/commits/{HEAD_SHA}/pulls"]


def test_unhinted_signal_with_multiple_trusted_prs_fails_closed() -> None:
    api = FakeApi(payload=[candidate(681), candidate(682)])

    with pytest.raises(RuntimeError, match="multiple trusted PRs"):
        resolve_pr_number(
            api,
            repo=REPO,
            hinted_number=0,
            head_sha=HEAD_SHA,
            head_ref=HEAD_REF,
            default_branch="main",
        )


def test_hinted_pr_identity_mismatch_still_fails_closed() -> None:
    api = FakeApi(payload=candidate(681, head_ref="different-head"))

    with pytest.raises(RuntimeError, match="hint failed"):
        resolve_pr_number(
            api,
            repo=REPO,
            hinted_number=681,
            head_sha=HEAD_SHA,
            head_ref=HEAD_REF,
            default_branch="main",
        )


def test_main_skips_zero_match_without_calling_privileged_drainer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = FakeApi(payload=[])
    monkeypatch.setattr(adapter, "GitHubApi", lambda _token: api)

    def unexpected_drain() -> int:
        raise AssertionError("privileged drainer must not run without a trusted PR")

    monkeypatch.setattr(adapter, "drain_main", unexpected_drain)
    env = {
        "GH_TOKEN": "test-token",
        "REPO": REPO,
        "EVENT_HEAD_REPO": REPO,
        "EVENT_HEAD_REF": HEAD_REF,
        "EVENT_HEAD_SHA": HEAD_SHA,
        "DEFAULT_BRANCH": "main",
        "PR_NUMBER": "",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    assert adapter.main() == 0
    assert api.paths == [f"/repos/{REPO}/commits/{HEAD_SHA}/pulls"]


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
