from __future__ import annotations

import pytest

from scripts.pr_obsolete_run_from_workflow_run import parse_pr_hints_json, resolve_pr_numbers

REPO = "Apeloff1/Skeleton"
HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"


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
        if path == f"/repos/{REPO}/pulls/556":
            return 200, pull(556), {}
        if "/commits/" in path and "/pulls" in path:
            return 200, [], {}
        raise AssertionError(path)

    api = FakeApi(handler)
    assert resolve_pr_numbers(
        api,
        repo=REPO,
        hinted_numbers=[556],
        head_sha=HEAD_SHA,
        head_ref="feature/drain",
        default_branch="main",
    ) == [556]


def test_mismatched_hint_is_skipped_and_sha_recovery_still_runs() -> None:
    def handler(method: str, path: str):
        assert method == "GET"
        if path == f"/repos/{REPO}/pulls/556":
            return 200, pull(556, base="release"), {}
        if "/commits/" in path and "/pulls" in path:
            return 200, [pull(900)], {}
        raise AssertionError(path)

    api = FakeApi(handler)
    assert resolve_pr_numbers(
        api,
        repo=REPO,
        hinted_numbers=[556],
        head_sha=HEAD_SHA,
        head_ref="feature/drain",
        default_branch="main",
    ) == [900]


def test_empty_workflow_run_pull_metadata_recovers_every_matching_pr() -> None:
    def handler(method: str, path: str):
        assert method == "GET"
        assert "/commits/" in path and "/pulls" in path
        return 200, [pull(556), pull(900, head_ref="other"), pull(557)], {}

    api = FakeApi(handler)
    assert resolve_pr_numbers(
        api,
        repo=REPO,
        hinted_numbers=[],
        head_sha=HEAD_SHA,
        head_ref="feature/drain",
        default_branch="main",
    ) == [556, 557]


def test_commit_association_keeps_every_trusted_pr() -> None:
    api = FakeApi(lambda method, path: (200, [pull(556), pull(557)], {}))
    assert resolve_pr_numbers(
        api,
        repo=REPO,
        hinted_numbers=[],
        head_sha=HEAD_SHA,
        head_ref="feature/drain",
        default_branch="main",
    ) == [556, 557]


def test_default_branch_signal_is_rejected_before_api_access() -> None:
    api = FakeApi(lambda method, path: (_ for _ in ()).throw(AssertionError(path)))
    with pytest.raises(RuntimeError, match="default branch"):
        resolve_pr_numbers(
            api,
            repo=REPO,
            hinted_numbers=[],
            head_sha=HEAD_SHA,
            head_ref="main",
            default_branch="main",
        )


def test_parse_pr_hints_json_keeps_every_valid_number() -> None:
    assert parse_pr_hints_json("") == []
    assert parse_pr_hints_json("[]") == []
    assert parse_pr_hints_json("null") == []
    assert parse_pr_hints_json("[11, 12, 11]") == [11, 12]


def test_parse_pr_hints_json_fails_closed_on_malformed_payloads() -> None:
    with pytest.raises(RuntimeError, match="JSON array"):
        parse_pr_hints_json('{"number": 11}')
    with pytest.raises(RuntimeError, match="invalid workflow_run PR hint JSON"):
        parse_pr_hints_json("[11,")
    with pytest.raises(RuntimeError, match="invalid workflow_run PR hint"):
        parse_pr_hints_json("[true]")
    with pytest.raises(RuntimeError, match="invalid workflow_run PR hint"):
        parse_pr_hints_json('["11"]')
    with pytest.raises(RuntimeError, match="invalid workflow_run PR hint"):
        parse_pr_hints_json("[0]")
