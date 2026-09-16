from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "branch-clean.yml"


def test_branch_cleanup_protects_fresh_refs_before_ancestry_deletion() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "BRANCH_CLEAN_GRACE_SECONDS: '1800'" in text
    assert 'select(.type == "CreateEvent" and .payload.ref_type == "branch")' in text
    assert "recent_branch_creations[\"$ref\"]=1" in text
    assert "recent-create-event" in text
    assert "exact-current-main" in text
    assert "recent-merged-tip" in text

    recent_create_guard = text.index('recent_branch_creations[$branch]+x')
    exact_main_guard = text.index('[[ "$tip" == "$classified_main" ]]')
    ancestor_guard = text.index('git merge-base --is-ancestor "$tip" "$main_ref"')
    deletion_candidate = text.index('delete_branches+=("$branch")')

    assert recent_create_guard < deletion_candidate
    assert exact_main_guard < deletion_candidate
    assert ancestor_guard < deletion_candidate
    assert text.index("tip_age < BRANCH_CLEAN_GRACE_SECONDS") < deletion_candidate


def test_branch_cleanup_fails_closed_without_creation_age_signal() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "if ! load_recent_branch_creations; then" in text
    assert "no refs will be deleted" in text
    assert "No branch refs were deleted because creation-age safety could not be established." in text


def test_branch_cleanup_keeps_existing_race_guards() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "open-pr-head" in text
    assert "open-pr-head-late" in text
    assert '[[ "$current_main" != "$classified_main" ]]' in text
    assert "--force-with-lease=refs/heads/${branch}:${tip}" in text
    assert "git push --quiet --atomic" in text
