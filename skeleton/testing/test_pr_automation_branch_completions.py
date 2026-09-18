from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from skeleton.pr_automation.runner import (
    GitHubError,
    _publish_run_error,
    _status_url,
    canonical_commit_oid,
    fetch_snapshot,
    parse_pr_hints_json,
    resolve_branch_completion_prs,
    select_evaluation_targets,
)

REPO = "Apeloff1/Skeleton"
HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"
BASE_SHA = "fedcba9876543210fedcba9876543210fedcba98"


def pull(
    number: int,
    *,
    base: str = "main",
    head_ref: str = "feat/branch-completions",
    repo: str = REPO,
    sha: str = HEAD_SHA,
    base_sha: str = BASE_SHA,
) -> dict[str, Any]:
    return {
        "number": number,
        "base": {"ref": base, "sha": base_sha},
        "head": {"ref": head_ref, "sha": sha, "repo": {"full_name": repo}},
    }


class FakeClient:
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[str] = []

    def get(self, path: str) -> Any:
        self.calls.append(path)
        return self.handler(path)


def test_empty_workflow_run_pull_metadata_recovers_every_matching_pr() -> None:
    def handler(path: str):
        if path.startswith(f"/repos/{REPO}/commits/{HEAD_SHA}/pulls"):
            return [
                pull(11),
                pull(12, base="develop"),
                pull(13, head_ref="other"),
                pull(14, repo="fork/Skeleton"),
            ]
        raise AssertionError(path)

    numbers = resolve_branch_completion_prs(
        FakeClient(handler),
        repository=REPO,
        head_sha=HEAD_SHA,
        head_ref="feat/branch-completions",
        allowed_bases=("main", "develop"),
    )
    assert numbers == [11, 12]


def test_event_pr_hint_is_kept_when_commit_association_is_empty() -> None:
    def handler(path: str):
        if path == f"/repos/{REPO}/pulls/77":
            return pull(77)
        if path.startswith(f"/repos/{REPO}/commits/{HEAD_SHA}/pulls"):
            return []
        raise AssertionError(path)

    numbers = resolve_branch_completion_prs(
        FakeClient(handler),
        repository=REPO,
        head_sha=HEAD_SHA,
        head_ref="feat/branch-completions",
        allowed_bases=("main",),
        hinted_numbers=[77],
    )
    assert numbers == [77]


def test_branch_history_recovers_exact_sha_when_commit_association_is_empty() -> None:
    def handler(path: str):
        if path.startswith(f"/repos/{REPO}/commits/{HEAD_SHA}/pulls"):
            return []
        if "/pulls?" in path and "head=" in path:
            return [pull(88, sha=HEAD_SHA), pull(89, sha="old-tip")]
        raise AssertionError(path)

    numbers = resolve_branch_completion_prs(
        FakeClient(handler),
        repository=REPO,
        head_sha=HEAD_SHA,
        head_ref="feat/branch-completions",
        allowed_bases=("main",),
    )
    assert numbers == [88]


def test_reused_branch_name_without_sha_match_is_not_attributed() -> None:
    def handler(path: str):
        if path.startswith(f"/repos/{REPO}/commits/{HEAD_SHA}/pulls"):
            return []
        if "/pulls?" in path:
            return [pull(90, sha="someone-else")]
        raise AssertionError(path)

    numbers = resolve_branch_completion_prs(
        FakeClient(handler),
        repository=REPO,
        head_sha=HEAD_SHA,
        head_ref="feat/branch-completions",
        allowed_bases=("main",),
    )
    assert numbers == []


def test_disallowed_bases_and_forks_never_enter_the_completion_set() -> None:
    def handler(path: str):
        if path.startswith(f"/repos/{REPO}/commits/{HEAD_SHA}/pulls"):
            return [
                pull(21, base="release"),
                pull(22, repo="other/Skeleton"),
            ]
        if "/pulls?" in path:
            return []
        raise AssertionError(path)

    numbers = resolve_branch_completion_prs(
        FakeClient(handler),
        repository=REPO,
        head_sha=HEAD_SHA,
        head_ref="feat/branch-completions",
        allowed_bases=("main",),
    )
    assert numbers == []


def test_incomplete_commit_association_scan_fails_closed() -> None:
    def handler(path: str):
        if path.startswith(f"/repos/{REPO}/commits/{HEAD_SHA}/pulls"):
            return [pull(n) for n in range(1, 101)]
        raise AssertionError(path)

    with pytest.raises(GitHubError, match="bounded identity scan"):
        resolve_branch_completion_prs(
            FakeClient(handler),
            repository=REPO,
            head_sha=HEAD_SHA,
            head_ref="feat/branch-completions",
            allowed_bases=("main",),
        )


def test_missing_branch_identity_fails_closed() -> None:
    with pytest.raises(GitHubError, match="head SHA and branch"):
        resolve_branch_completion_prs(
            FakeClient(lambda path: []),
            repository=REPO,
            head_sha=HEAD_SHA,
            head_ref="",
            allowed_bases=("main",),
        )


def test_invalid_hint_fails_closed() -> None:
    with pytest.raises(GitHubError, match="invalid hinted PR"):
        resolve_branch_completion_prs(
            FakeClient(lambda path: []),
            repository=REPO,
            head_sha=HEAD_SHA,
            head_ref="feat/branch-completions",
            allowed_bases=("main",),
            hinted_numbers=[0],
        )


def test_uppercase_head_sha_is_canonicalized_before_lookup() -> None:
    def handler(path: str):
        assert f"/commits/{HEAD_SHA}/pulls" in path
        assert HEAD_SHA.upper() not in path
        return [pull(11)]

    numbers = resolve_branch_completion_prs(
        FakeClient(handler),
        repository=REPO,
        head_sha=HEAD_SHA.upper(),
        head_ref="feat/branch-completions",
        allowed_bases=("main",),
    )
    assert numbers == [11]
    assert canonical_commit_oid(HEAD_SHA.upper()) == HEAD_SHA


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
    with pytest.raises(GitHubError, match="40-character hex commit OID"):
        resolve_branch_completion_prs(
            FakeClient(lambda path: (_ for _ in ()).throw(AssertionError(path))),
            repository=REPO,
            head_sha=head_sha,
            head_ref="feat/branch-completions",
            allowed_bases=("main",),
        )


def test_feature_branch_completion_does_not_fall_back_to_unrelated_sweep() -> None:
    def handler(path: str):
        if path.startswith(f"/repos/{REPO}/commits/{HEAD_SHA}/pulls"):
            return []
        if "state=open" in path:
            raise AssertionError("feature-branch completion must not scan unrelated PRs")
        if "/pulls?" in path:
            return []
        raise AssertionError(path)

    numbers = select_evaluation_targets(
        FakeClient(handler),
        repository=REPO,
        explicit_pr=None,
        head_sha=HEAD_SHA,
        head_ref="feat/branch-completions",
        default_branch="main",
        allowed_bases=("main",),
        hinted_numbers=[],
        limit=25,
    )
    assert numbers == []


def test_default_branch_completion_sweeps_open_prs() -> None:
    def handler(path: str):
        if "state=open" in path:
            return [{"number": 5}, {"number": 6}]
        raise AssertionError(path)

    numbers = select_evaluation_targets(
        FakeClient(handler),
        repository=REPO,
        explicit_pr=None,
        head_sha=HEAD_SHA,
        head_ref="main",
        default_branch="main",
        allowed_bases=("main",),
        hinted_numbers=[],
        limit=25,
    )
    assert numbers == [5, 6]


def test_malformed_default_branch_head_sha_does_not_sweep_open_prs() -> None:
    with pytest.raises(GitHubError, match="40-character hex commit OID"):
        select_evaluation_targets(
            FakeClient(lambda path: (_ for _ in ()).throw(AssertionError(path))),
            repository=REPO,
            explicit_pr=None,
            head_sha="mainsha",
            head_ref="main",
            default_branch="main",
            allowed_bases=("main",),
            hinted_numbers=[],
            limit=25,
        )


def test_explicit_pr_wins_over_branch_completion_identity() -> None:
    numbers = select_evaluation_targets(
        FakeClient(lambda path: (_ for _ in ()).throw(AssertionError(path))),
        repository=REPO,
        explicit_pr=42,
        head_sha=HEAD_SHA,
        head_ref="feat/branch-completions",
        default_branch="main",
        allowed_bases=("main",),
        hinted_numbers=[77],
        limit=25,
    )
    assert numbers == [42]


def test_partial_workflow_run_identity_fails_closed() -> None:
    with pytest.raises(GitHubError, match="head SHA and branch"):
        select_evaluation_targets(
            FakeClient(lambda path: []),
            repository=REPO,
            explicit_pr=None,
            head_sha=HEAD_SHA,
            head_ref="",
            default_branch="main",
            allowed_bases=("main",),
            hinted_numbers=[],
            limit=25,
        )


def test_fetch_snapshot_rejects_malformed_pr_head_sha_before_commit_lookup() -> None:
    def handler(path: str):
        if path == f"/repos/{REPO}/pulls/11":
            return pull(11, sha="abc123")
        raise AssertionError(path)

    client = FakeClient(handler)
    with pytest.raises(GitHubError, match="40-character hex commit OID"):
        fetch_snapshot(client, REPO, 11, set())
    assert client.calls == [f"/repos/{REPO}/pulls/11"]


def test_fetch_snapshot_quotes_canonical_head_sha_for_commit_lookups() -> None:
    def handler(path: str):
        if path == f"/repos/{REPO}/pulls/11":
            return {
                **pull(11),
                "state": "open",
                "merged": False,
                "draft": False,
                "mergeable": True,
                "mergeable_state": "clean",
                "changed_files": 1,
                "additions": 1,
                "deletions": 0,
                "labels": [],
            }
        if path.startswith(f"/repos/{REPO}/commits/{HEAD_SHA}/check-runs"):
            return {"total_count": 0, "check_runs": []}
        if path.startswith(f"/repos/{REPO}/commits/{HEAD_SHA}/statuses"):
            return []
        if path.startswith(f"/repos/{REPO}/pulls/11/reviews"):
            return []
        if path.startswith(f"/repos/{REPO}/pulls/11/files"):
            return []
        raise AssertionError(path)

    class SnapshotClient(FakeClient):
        def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
            raise GitHubError("threads unused")

    snapshot, _ = fetch_snapshot(SnapshotClient(handler), REPO, 11, set())
    assert snapshot.head_sha == HEAD_SHA
    assert snapshot.base_sha == BASE_SHA


def test_fetch_snapshot_rejects_malformed_pr_base_sha_before_commit_lookup() -> None:
    def handler(path: str):
        if path == f"/repos/{REPO}/pulls/11":
            return pull(11, base_sha="abc123")
        raise AssertionError(path)

    client = FakeClient(handler)
    with pytest.raises(GitHubError, match="40-character hex commit OID"):
        fetch_snapshot(client, REPO, 11, set())
    assert client.calls == [f"/repos/{REPO}/pulls/11"]


def test_status_url_quotes_canonical_commit_oid() -> None:
    url = _status_url(REPO, HEAD_SHA.upper())
    assert url.endswith(f"/statuses/{HEAD_SHA}")
    assert HEAD_SHA.upper() not in url


def test_publish_run_error_skips_malformed_live_head_sha() -> None:
    def handler(path: str):
        if path == f"/repos/{REPO}/pulls/11":
            return pull(11, sha="abc123")
        raise AssertionError(path)

    class RecordingClient(FakeClient):
        def request(self, method: str, url: str, body=None):
            raise AssertionError(f"unexpected request {method} {url}")

    _publish_run_error(RecordingClient(handler), REPO, 11, "boom")


def test_publish_run_error_posts_canonical_quoted_status() -> None:
    posted: list[tuple[str, str]] = []

    def handler(path: str):
        if path == f"/repos/{REPO}/pulls/11":
            return pull(11, sha=HEAD_SHA.upper())
        raise AssertionError(path)

    class RecordingClient(FakeClient):
        def request(self, method: str, url: str, body=None):
            posted.append((method, url))
            return {}

    _publish_run_error(RecordingClient(handler), REPO, 11, "boom")
    assert posted == [("POST", _status_url(REPO, HEAD_SHA))]


def test_parse_pr_hints_json_keeps_every_valid_number() -> None:
    assert parse_pr_hints_json("") == []
    assert parse_pr_hints_json("[]") == []
    assert parse_pr_hints_json("null") == []
    assert parse_pr_hints_json("[11, 12, 11]") == [11, 12]


def test_parse_pr_hints_json_fails_closed_on_malformed_payloads() -> None:
    with pytest.raises(GitHubError, match="JSON array"):
        parse_pr_hints_json('{"number": 11}')
    with pytest.raises(GitHubError, match="invalid workflow_run PR hint JSON"):
        parse_pr_hints_json("[11,")
    with pytest.raises(GitHubError, match="invalid workflow_run PR hint"):
        parse_pr_hints_json("[true]")
    with pytest.raises(GitHubError, match="invalid workflow_run PR hint"):
        parse_pr_hints_json('["11"]')
    with pytest.raises(GitHubError, match="invalid workflow_run PR hint"):
        parse_pr_hints_json("[0]")


def test_workflow_run_consumers_match_every_completing_branch() -> None:
    root = Path(__file__).resolve().parents[2]
    workflows = root / ".github" / "workflows"
    expected = 'branches:\n      - "*"\n      - "**"'
    consumers = {
        "repair-intake.yml": "types: [completed]",
        "idle-studio.yml": "types: [completed]",
        "pr-obsolete-run-drain.yml": "types: [requested]",
    }
    for name, event_type in consumers.items():
        text = (workflows / name).read_text(encoding="utf-8")
        assert "workflow_run:" in text
        assert event_type in text
        assert expected in text, f"{name} must match every completing head"
        assert "pull_requests[0]" not in text, f"{name} must not treat pull_requests[0] as identity"
    pr_automation = (workflows / "pr-automation-index.yml").read_text(encoding="utf-8")
    assert "workflow_run:" in pr_automation
    assert "types: [completed]" in pr_automation
    assert "branches-ignore:\n      - main" in pr_automation
    assert expected not in pr_automation
    assert "pull_requests[0]" not in pr_automation

    idle = (workflows / "idle-studio.yml").read_text(encoding="utf-8")
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in idle
    assert "exceeded bounded identity scan" in idle
    assert r"^[0-9a-f]{40}$" in idle
