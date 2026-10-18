from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "branch-clean.yml"


def _source() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_branch_cleanup_requires_positive_creation_age_before_deletion() -> None:
    text = _source()

    assert "BRANCH_CLEAN_GRACE_SECONDS: '1800'" in text
    assert 'select((.type == "CreateEvent" or .type == "DeleteEvent") and .payload.ref_type == "branch")' in text
    assert 'branch_creation_epochs["$ref"]="$created_epoch"' in text
    assert "creation-age-unknown" in text
    assert "recent-create-event" in text
    assert "exact-current-main" in text
    assert "recent-tip" in text

    unknown_creation_guard = text.index('branch_creation_epochs[$branch]+x')
    creation_grace_guard = text.index("creation_age < BRANCH_CLEAN_GRACE_SECONDS")
    exact_main_guard = text.index('[[ "$tip" == "$classified_main" ]]')
    commit_age_lookup = text.index('committed_at=$(git show -s --format=%cI "$tip"')
    deletion_candidate = text.index('delete_branches+=("$branch")')

    assert unknown_creation_guard < creation_grace_guard < exact_main_guard
    assert exact_main_guard < commit_age_lookup < deletion_candidate
    assert text.index("tip_age < BRANCH_CLEAN_GRACE_SECONDS") < deletion_candidate


def test_branch_cleanup_never_uses_commit_age_as_creation_age_fallback() -> None:
    text = _source()

    unknown_creation_guard = text.index(
        'if [[ -z "${branch_creation_epochs[$branch]+x}" ]]; then'
    )
    delayed_create_guard = text.index("deletion_epoch >= creation_epoch")
    commit_age_lookup = text.index('committed_at=$(git show -s --format=%cI "$tip"')
    deletion_candidate = text.index('delete_branches+=("$branch")')

    assert unknown_creation_guard < delayed_create_guard < commit_age_lookup
    assert commit_age_lookup < deletion_candidate
    # Missing creation history preserves all unmerged branches. A prior
    # matching, grace-aged merged-PR head is the sole audited exception.
    assert 'if [[ -z "${merged_pr_head_tips[$merged_key]+x}" ]]; then' in text
    assert 'printf \'%s %s creation-age-unknown\\n\'' in text
    assert 'merged_without_create_count=$((merged_without_create_count + 1))' in text


def test_branch_cleanup_preserves_delayed_recreation() -> None:
    text = _source()

    assert 'branch_deletion_epochs["$ref"]="$created_epoch"' in text
    assert "delayed-create-event" in text
    assert (
        "A DeleteEvent at or after the latest CreateEvent preserves the live ref "
        "as a delayed recreation."
    ) in text

    delayed_create_guard = text.index("deletion_epoch >= creation_epoch")
    deletion_candidate = text.index('delete_branches+=("$branch")')
    assert delayed_create_guard < deletion_candidate


def test_exact_main_new_branch_is_never_a_cleanup_candidate() -> None:
    text = _source()

    exact_main_guard = text.index('[[ "$tip" == "$classified_main" ]]')
    exact_main_preserve = text.index("exact-current-main")
    first_candidate = text.index('delete_branches+=("$branch")')

    assert exact_main_guard < exact_main_preserve < first_candidate
    assert (
        "Exact-current-main branches are preserved so new work branches can receive "
        "their first commit safely."
    ) in text


def test_branch_cleanup_api_dependencies_fail_closed() -> None:
    text = _source()

    assert text.count("if ! gh api --paginate") >= 3
    assert 'candidate_file="$RUNNER_TEMP/open-pr-refs.candidate.tsv"' in text
    assert 'if ! mv -f "$candidate_file" "$refs_file"; then' in text
    assert "if ! load_open_pr_refs; then" in text
    assert "if ! load_merged_pr_head_tips; then" in text
    assert "if ! load_branch_creation_history; then" in text
    assert "Late open pull-request revalidation failed." in text
    assert "Failure to load PR refs, merged-PR evidence, or branch-event history produces zero deletions." in text

    first_pr_guard = text.index("if ! load_open_pr_refs; then")
    merged_guard = text.index("if ! load_merged_pr_head_tips; then")
    history_guard = text.index("if ! load_branch_creation_history; then")
    late_guard = text.index("Late open pull-request revalidation failed.")
    deletion_push = text.index("git push --quiet --atomic")

    assert first_pr_guard < merged_guard < history_guard < late_guard < deletion_push


def test_branch_cleanup_preserves_stacked_pr_heads_and_bases() -> None:
    text = _source()

    assert 'open_pr_heads["$head"]=1' in text
    assert 'open_pr_bases["$base"]=1' in text
    assert "open-pr-head" in text
    assert "open-pr-base" in text
    assert "open-pr-head-late" in text
    assert "open-pr-base-late" in text


def test_branch_cleanup_keeps_all_redundancy_proofs_and_race_leases() -> None:
    text = _source()

    assert 'merged_pr_head_tips["${branch}:${tip}"]=1' in text
    assert 'git merge-base --is-ancestor "$tip" "$main_ref"' in text
    assert 'git rev-parse "$tip^{tree}"' in text
    assert '[[ "$current_main" != "$classified_main" ]]' in text
    assert "--force-with-lease=refs/heads/${branch}:${tip}" in text
    assert "git push --quiet --atomic" in text


def test_branch_cleanup_trigger_is_bounded() -> None:
    text = _source()

    # The cleanup worker is intentionally operator-dispatched only: untrusted
    # event churn must not trigger automatic branch deletion on a saturated
    # repository. Exact-tip leases and API revalidation remain mandatory.
    trigger = text.split("jobs:", 1)[0]
    assert "on:\n  workflow_dispatch:" in trigger
    assert "workflow_run:" not in trigger
    assert "schedule:" not in trigger
    assert "group: branch-clean-v4-\u0024{{ github.repository }}" in trigger
    assert "cancel-in-progress: false" in trigger
    assert "runs-on: ubuntu-24.04-arm" in text
    assert "timeout-minutes: 15" in text
