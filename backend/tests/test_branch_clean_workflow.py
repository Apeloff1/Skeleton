from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "branch-clean.yml"


def _source() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_branch_cleanup_requires_positive_creation_and_tip_age() -> None:
    text = _source()

    assert "BRANCH_CLEAN_GRACE_SECONDS: '1800'" in text
    assert "creation-age-unknown" in text
    assert "recent-create-event" in text
    assert "delayed-create-event" in text
    assert "recent-tip" in text
    assert "tip-age-unavailable" in text

    creation_guard = text.index('branch_creation_epochs[$branch]+x')
    delayed_guard = text.index("deletion_epoch >= creation_epoch")
    creation_grace = text.index("creation_age < BRANCH_CLEAN_GRACE_SECONDS")
    tip_grace = text.index("tip_age < BRANCH_CLEAN_GRACE_SECONDS")
    first_candidate = text.index('merged_key="${branch}:${tip}"')

    assert creation_guard < delayed_guard < creation_grace < tip_grace < first_candidate


def test_exact_main_is_preserved_not_deleted() -> None:
    text = _source()

    exact_main = text.index('elif [[ "$tip" == "$classified_main" ]]')
    preserve = text.index("exact-current-main", exact_main)
    next_candidate = text.index('elif git merge-base --is-ancestor "$tip" "$main_ref"', exact_main)
    segment = text[exact_main:next_candidate]

    assert preserve < next_candidate
    assert 'delete_branches+=("$branch")' not in segment
    assert "continue" in segment


def test_open_pr_head_and_base_reads_fail_closed() -> None:
    text = _source()

    assert 'heads_file="$RUNNER_TEMP/open-pr-heads.txt"' in text
    assert 'bases_file="$RUNNER_TEMP/open-pr-bases.txt"' in text
    assert "could not load open pull-request heads" in text
    assert "could not load open pull-request bases" in text
    assert "No branch refs were deleted because PR protection could not be established." in text
    assert "No branch refs were deleted because PR protection could not be re-established." in text
    assert "open-pr-head" in text
    assert "open-pr-base" in text
    assert "open-pr-head-late" in text
    assert "open-pr-base-late" in text


def test_creation_history_api_failure_is_non_mutating() -> None:
    text = _source()

    assert 'select((.type == "CreateEvent" or .type == "DeleteEvent") and .payload.ref_type == "branch")' in text
    assert "if ! load_branch_creation_history; then" in text
    assert "No branch refs were deleted because creation-age safety could not be established." in text


def test_new_guards_preserve_current_main_cleanup_proofs() -> None:
    text = _source()

    assert "branch-clean-v2-" in text
    assert "merged_pr_head_tips" in text
    assert "merged-pr-head" in text or "Merged-PR exact-head refs eligible" in text
    assert "identical_tree_count" in text
    assert "tree identical to current main" in text
    assert "open-pr-base" in text
    assert '[[ "$current_main" != "$classified_main" ]]' in text
    assert "--force-with-lease=refs/heads/${branch}:${tip}" in text
    assert "git push --quiet --atomic" in text
