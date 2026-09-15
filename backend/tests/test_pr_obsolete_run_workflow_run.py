from __future__ import annotations

import pytest

from scripts.pr_obsolete_run_from_workflow_run import resolve_pr_number

REPO = "Apeloff1/Skeleton"


class FakeApi:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def request(self, path: str, *, method: str = "GET"):
        self.calls.append((method, path))
        return self.handler(method, path)


def pull(
    number: int,
    *,
    base: str = "main",
    head_ref: str = "feature/drain",
    repo: str = REPO,
):
    return {
        "number": number,
        "base": {"ref": base},
        "head": {"ref": head_ref, "repo": {"full_name": repo}},
    }


def test_hinted_pr_is_validated_before_privileged_cleanup() -> None:
    def handler(method: str, path: str):
        assert method == "GET"
        assert path == f"/repos/{REPO}/pulls/556"
        return 200, pull(556), {}

    api = FakeApi(handler)
    assert resolve_pr_number(
        api,
        repo=REPO,
        hinted_number=556,
        head_sha="abc123",
        head_ref="feature/drain",
        default_branch="main",
    ) == 556


def test_hinted_pr_targeting_other_base_fails_closed() -> None:
    api = FakeApi(lambda method, path: (200, pull(556, base="release"), {}))
    with pytest.raises(RuntimeError, match="base validation"):
        resolve_pr_number(
            api,
            repo=REPO,
            hinted_number=556,
            head_sha="abc123",
            head_ref="feature/drain",
            default_branch="main",
        )


def test_empty_workflow_run_pull_metadata_recovers_from_commit_association() -> None:
    def handler(method: str, path: str):
        assert method == "GET"
        assert path == f"/repos/{REPO}/commits/abc123/pulls"
        return 200, [pull(556), pull(900, head_ref="other")], {}

    api = FakeApi(handler)
    assert resolve_pr_number(
        api,
        repo=REPO,
        hinted_number=0,
        head_sha="abc123",
        head_ref="feature/drain",
        default_branch="main",
    ) == 556


def test_ambiguous_commit_association_fails_closed() -> None:
    api = FakeApi(lambda method, path: (200, [pull(556), pull(557)], {}))
    with pytest.raises(RuntimeError, match="exactly one trusted PR"):
        resolve_pr_number(
            api,
            repo=REPO,
            hinted_number=0,
            head_sha="abc123",
            head_ref="feature/drain",
            default_branch="main",
        )


def test_default_branch_signal_is_rejected_before_api_access() -> None:
    api = FakeApi(lambda method, path: (_ for _ in ()).throw(AssertionError(path)))
    with pytest.raises(RuntimeError, match="default branch"):
        resolve_pr_number(
            api,
            repo=REPO,
            hinted_number=0,
            head_sha="abc123",
            head_ref="main",
            default_branch="main",
        )
