from __future__ import annotations

from pathlib import Path

import pytest

import scripts.pr_churn_control as churn
from scripts.pr_churn_control import (
    ABSOLUTE_MAX_MUTATIONS,
    Retirement,
    _bounded_mutation_limit,
    build_retirement_plan,
    eligible_pair,
    superseded_numbers,
)


REPO = "Apeloff1/Skeleton"
AUTHOR = "Apeloff1"


def _pr(
    number: int,
    *,
    body: str = "",
    created_at: str | None = None,
    title: str = "fix: focused repair",
    state: str = "open",
    draft: bool = False,
    author: str = AUTHOR,
    head_repo: str = REPO,
    base: str = "main",
    labels: tuple[str, ...] = (),
    merged: bool = False,
) -> dict[str, object]:
    if created_at is None:
        created_at = f"2026-09-16T19:{number % 60:02d}:00Z"
    return {
        "number": number,
        "body": body,
        "created_at": created_at,
        "title": title,
        "state": state,
        "draft": draft,
        "merged": merged,
        "merged_at": "2026-09-16T20:00:00Z" if merged else None,
        "user": {"login": author},
        "head": {
            "ref": f"repair/{number}",
            "sha": f"sha-{number}",
            "repo": {"full_name": head_repo},
        },
        "base": {"ref": base},
        "labels": [{"name": label} for label in labels],
    }


def test_supersedence_parser_supports_multiple_refs_and_ignores_untrusted_regions() -> None:
    body = """
Supersedes #10 and #11.
This PR supersedes duplicate #12; repository CI remains authoritative.

> Supersedes #13.

```text
Supersedes #14.
```
"""

    assert superseded_numbers(body) == (10, 11, 12)


def test_explicit_newer_owner_pr_can_retire_older_owner_pr() -> None:
    source = _pr(
        220,
        body="Supersedes stale PR #120.",
        created_at="2026-09-16T20:20:00Z",
    )
    target = _pr(120, created_at="2026-09-16T18:20:00Z")

    assert eligible_pair(
        source,
        target,
        repo=REPO,
        default_branch="main",
        trusted_author=AUTHOR,
    ) == (True, "explicit trusted supersedence")


@pytest.mark.parametrize(
    ("source_patch", "reason"),
    [
        ({"draft": True}, "source is not an active trusted same-repository PR"),
        (
            {"title": "[validation] combined stack"},
            "source is not an active trusted same-repository PR",
        ),
        (
            {"user": {"login": "other-user"}},
            "source is not an active trusted same-repository PR",
        ),
        (
            {"head": {"ref": "repair/220", "repo": {"full_name": "fork/repo"}}},
            "source is not an active trusted same-repository PR",
        ),
    ],
)
def test_untrusted_or_validation_sources_cannot_retire(
    source_patch: dict[str, object],
    reason: str,
) -> None:
    source = _pr(
        220,
        body="Supersedes #120.",
        created_at="2026-09-16T20:20:00Z",
    )
    source.update(source_patch)
    target = _pr(120, created_at="2026-09-16T18:20:00Z")

    assert eligible_pair(
        source,
        target,
        repo=REPO,
        default_branch="main",
        trusted_author=AUTHOR,
    ) == (False, reason)


def test_preserve_label_is_a_hard_escape_hatch() -> None:
    source = _pr(
        220,
        body="Supersedes #120.",
        created_at="2026-09-16T20:20:00Z",
    )
    target = _pr(
        120,
        created_at="2026-09-16T18:20:00Z",
        labels=("churn/preserve",),
    )

    allowed, reason = eligible_pair(
        source,
        target,
        repo=REPO,
        default_branch="main",
        trusted_author=AUTHOR,
    )

    assert allowed is False
    assert reason == "target carries an explicit preserve label"


def test_newest_explicit_source_wins_and_plan_respects_mutation_cap() -> None:
    target_a = _pr(100, created_at="2026-09-16T17:00:00Z")
    target_b = _pr(101, created_at="2026-09-16T17:01:00Z")
    older_source = _pr(
        200,
        body="Supersedes #100 and #101.",
        created_at="2026-09-16T18:00:00Z",
    )
    newer_source = _pr(
        300,
        body="Supersedes #100 and #101.",
        created_at="2026-09-16T19:00:00Z",
    )

    plan = build_retirement_plan(
        [target_a, target_b, older_source, newer_source],
        repo=REPO,
        default_branch="main",
        trusted_author=AUTHOR,
        max_mutations=1,
    )

    assert plan == [Retirement(source_number=300, target_number=100)]


def test_mutation_limit_is_always_bounded() -> None:
    assert _bounded_mutation_limit("0") == 1
    assert _bounded_mutation_limit("not-a-number") == churn.DEFAULT_MAX_MUTATIONS
    assert _bounded_mutation_limit("999999") == ABSOLUTE_MAX_MUTATIONS


def test_workflow_runs_only_from_trusted_default_branch_context() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/pr-churn-control.yml").read_text(
        encoding="utf-8"
    )

    assert "pull_request_target:" not in workflow
    assert "pull_request:" not in workflow
    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
    assert "branches: [main]" in workflow
    assert "permissions: {}" in workflow
    assert "contents: read" in workflow
    assert "pull-requests: write" in workflow
    assert "actions: write" not in workflow
    assert "persist-credentials: false" in workflow
    assert "python backend/scripts/pr_churn_control.py" in workflow
    assert "cancel-in-progress: false" in workflow


def test_churn_recovery_control_plane_uses_broad_runner_pool() -> None:
    root = Path(__file__).resolve().parents[2]
    for relative in (
        ".github/workflows/pr-churn-control.yml",
        ".github/workflows/queue-drain.yml",
    ):
        workflow = (root / relative).read_text(encoding="utf-8")
        assert "runs-on: ubuntu-latest" in workflow
        assert "runs-on: ubuntu-24.04-arm" not in workflow
