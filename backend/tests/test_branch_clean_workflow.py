from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "branch-clean.yml"


def test_branch_cleanup_requires_positive_creation_age_before_deletion() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "BRANCH_CLEAN_GRACE_SECONDS: '1800'" in text
    assert 'select(.type == "CreateEvent" and .payload.ref_type == "branch")' in text
    assert 'branch_creation_epochs["$ref"]="$created_epoch"' in text
    assert "creation-age-unknown" in text
    assert "recent-create-event" in text
    assert "exact-current-main" in text
    assert "recent-merged-tip" in text

    unknown_creation_guard = text.index('branch_creation_epochs[$branch]+x')
    creation_grace_guard = text.index("creation_age < BRANCH_CLEAN_GRACE_SECONDS")
    exact_main_guard = text.index('[[ "$tip" == "$classified_main" ]]')
    ancestor_guard = text.index('git merge-base --is-ancestor "$tip" "$main_ref"')
    deletion_candidate = text.index('delete_branches+=("$branch")')

    assert unknown_creation_guard < deletion_candidate
    assert creation_grace_guard < deletion_candidate
    assert exact_main_guard < deletion_candidate
    assert ancestor_guard < deletion_candidate
    assert text.index("tip_age < BRANCH_CLEAN_GRACE_SECONDS") < deletion_candidate


def test_branch_cleanup_never_uses_commit_age_as_missing_creation_age_fallback() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'if [[ -z "${branch_creation_epochs[$branch]+x}" ]]; then' in text
    assert "creation-age-unknown" in text
    assert "Missing branch creation history always preserves the ref." in text

    unknown_creation_guard = text.index('if [[ -z "${branch_creation_epochs[$branch]+x}" ]]; then')
    commit_age_lookup = text.index('committed_at=$(git show -s --format=%cI "$tip"')
    deletion_candidate = text.index('delete_branches+=("$branch")')

    assert unknown_creation_guard < commit_age_lookup < deletion_candidate


def test_branch_cleanup_fails_closed_without_creation_history_api() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "if ! load_branch_creation_history; then" in text
    assert "no refs will be deleted" in text
    assert "No branch refs were deleted because creation-age safety could not be established." in text


def test_branch_cleanup_keeps_existing_race_guards() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "open-pr-head" in text
    assert "open-pr-head-late" in text
    assert '[[ "$current_main" != "$classified_main" ]]' in text
    assert "--force-with-lease=refs/heads/${branch}:${tip}" in text
    assert "git push --quiet --atomic" in text
