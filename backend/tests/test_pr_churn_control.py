from __future__ import annotations

from pathlib import Path

import pytest

import scripts.pr_churn_control as churn
from scripts.pr_churn_control import (
    ABSOLUTE_MAX_MUTATIONS,
    Retirement,
    ReverseSyncRetirement,
    _bounded_mutation_limit,
    build_retirement_plan,
    build_reverse_sync_plan,
    eligible_pair,
    eligible_reverse_sync,
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
    head_ref: str | None = None,
    base: str = "main",
    base_repo: str = REPO,
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
            "ref": head_ref or f"repair/{number}",
            "sha": f"sha-{number}",
            "repo": {"full_name": head_repo},
        },
        "base": {"ref": base, "repo": {"full_name": base_repo}},
        "labels": [{"name": label} for label in labels],
    }


def test_supersedence_parser_requires_explicit_directives_and_ignores_untrusted_regions() -> None:
    body = """
Supersedes #10 and #11.
- Supersedes: duplicate #12; repository CI remains authoritative.
This PR supersedes duplicate #13.
This PR does not supersede #14.
No longer supersedes #15.

> Supersedes #16.

```text
Supersedes #17.
```
"""

    assert superseded_numbers(body) == (10, 11, 12)


def _sync_pr(
    number: int,
    *,
    base: str = "feature/stale",
    title: str | None = None,
    body: str | None = None,
    author: str = AUTHOR,
    head_repo: str = REPO,
    base_repo: str = REPO,
    labels: tuple[str, ...] = (),
    draft: bool = False,
) -> dict[str, object]:
    if title is None:
        title = f"chore(sync): refresh {base} from main"
    if body is None:
        body = (
            "Automated stale-branch refresh. Merge current `main` into this "
            "branch without rewriting branch history."
        )
    return _pr(
        number,
        body=body,
        title=title,
        draft=draft,
        author=author,
        head_repo=head_repo,
        head_ref="main",
        base=base,
        base_repo=base_repo,
        labels=labels,
    )


def test_exact_reverse_sync_automation_is_retirable() -> None:
    pr = _sync_pr(401, base="reconcile/runtime-current-main")

    assert eligible_reverse_sync(
        pr,
        repo=REPO,
        default_branch="main",
        trusted_author=AUTHOR,
    ) == (True, "exact trusted reverse-sync automation")

    assert build_reverse_sync_plan(
        [pr],
        repo=REPO,
        default_branch="main",
        trusted_author=AUTHOR,
        max_mutations=10,
    ) == [ReverseSyncRetirement(number=401)]


@pytest.mark.parametrize(
    "pr",
    [
        _sync_pr(402, title="chore(sync): refresh some-other-branch from main"),
        _sync_pr(403, body="human-authored branch refresh"),
        _sync_pr(404, author="other-user"),
        _sync_pr(405, head_repo="fork/repo"),
        _sync_pr(406, base_repo="other/repo"),
        _sync_pr(407, base="release/2026.09"),
        _sync_pr(408, base="keep/long-lived"),
        _sync_pr(409, base="backup/snapshot"),
        _sync_pr(410, base="archive/old"),
        _sync_pr(411, labels=("keep-open",)),
        _sync_pr(412, draft=True),
        {
            **_sync_pr(413),
            "number": 0,
        },
        _pr(
            414,
            title="chore(sync): refresh feature/stale from main",
            body=(
                "Automated stale-branch refresh. Merge current `main` into this "
                "branch without rewriting branch history."
            ),
            head_ref="feature/not-main",
            base="feature/stale",
        ),
    ],
)
def test_reverse_sync_retirement_is_fail_closed(pr: dict[str, object]) -> None:
    allowed, _ = eligible_reverse_sync(
        pr,
        repo=REPO,
        default_branch="main",
        trusted_author=AUTHOR,
    )
    assert allowed is False


def test_reverse_sync_requires_complete_same_repository_identity() -> None:
    missing_base_repo = _sync_pr(415)
    missing_base_repo["base"] = {"ref": "feature/stale"}

    allowed, reason = eligible_reverse_sync(
        missing_base_repo,
        repo=REPO,
        default_branch="main",
        trusted_author=AUTHOR,
    )

    assert allowed is False
    assert reason == "sync PR base is not same-repository"


def test_reverse_sync_plan_is_oldest_first_and_bounded() -> None:
    older = _sync_pr(420, base="reconcile/older")
    older["created_at"] = "2026-09-18T14:00:00Z"
    newer = _sync_pr(421, base="reconcile/newer")
    newer["created_at"] = "2026-09-18T14:01:00Z"

    assert build_reverse_sync_plan(
        [newer, older],
        repo=REPO,
        default_branch="main",
        trusted_author=AUTHOR,
        max_mutations=1,
    ) == [ReverseSyncRetirement(number=420)]


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

    churn_workflow = (
        root / ".github/workflows/pr-churn-control.yml"
    ).read_text(encoding="utf-8")
    assert "runs-on: ubuntu-latest" in churn_workflow
    assert "runs-on: ubuntu-24.04-arm" not in churn_workflow

    queue_workflow = (
        root / ".github/workflows/queue-drain.yml"
    ).read_text(encoding="utf-8")
    primary, helper = queue_workflow.split("  wake-housekeeping:", 1)
    assert "runs-on: ubuntu-latest" in primary
    assert "runs-on: ubuntu-24.04-arm" not in primary
    assert "runs-on: ubuntu-24.04-arm" in helper
