from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "branch-archive.yml"


def _source() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_branch_archive_trigger_is_bounded_and_trusted() -> None:
    text = _source()

    assert 'workflows: ["Prune redundant branches safely"]' in text
    assert "types: [completed]" in text
    assert "branches: [main]" in text
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in text
    assert "github.event.workflow_run.head_branch == github.event.repository.default_branch" in text
    assert "- cron: '7-57/10 * * * *'" in text
    assert "cancel-in-progress: false" in text


def test_branch_archive_includes_old_merged_and_unmerged_closed_heads() -> None:
    text = _source()

    assert ".closed_at != null and .closed_at <=" in text
    assert ".head.repo.full_name == .base.repo.full_name" in text
    assert ".merged_at == null" not in text
    assert "Archive candidates include merged and unmerged PRs closed for at least 24 hours." in text


def test_branch_archive_open_pr_protection_fails_closed() -> None:
    text = _source()

    assert 'heads_file="$RUNNER_TEMP/archive-open-heads.txt"' in text
    assert 'bases_file="$RUNNER_TEMP/archive-open-bases.txt"' in text
    assert "if ! gh api --paginate" in text
    assert "Branch archive could not load open pull-request heads" in text
    assert "Branch archive could not load open pull-request bases" in text
    assert "if ! load_open_refs; then" in text
    assert "Open pull-request revalidation failed during the sweep." in text

    first_guard = text.index("if ! load_open_refs; then")
    live_tip = text.index('live_tip=$(git ls-remote --heads origin')
    deletion = text.index('"--force-with-lease=refs/heads/${branch}:${tip}"')
    assert first_guard < live_tip < deletion


def test_branch_archive_candidate_inventory_fails_closed() -> None:
    text = _source()

    assert 'candidates_file="$RUNNER_TEMP/archive-candidates.tsv"' in text
    assert "Branch archive could not load closed pull-request heads" in text
    assert "if ! load_archive_candidates; then" in text
    assert "archive candidates could not be established" in text


def test_branch_archive_tags_exact_tip_before_lease_delete() -> None:
    text = _source()

    exact_live_tip = text.index('if [[ -z "$live_tip" || "$live_tip" != "$tip" ]]')
    tag_push = text.index('git push --quiet origin "${tip}:refs/tags/${tag}"')
    tag_verify = text.index('if [[ "$remote_tag" != "$tip" ]]')
    delete = text.index('"--force-with-lease=refs/heads/${branch}:${tip}"')

    assert exact_live_tip < tag_push < tag_verify < delete
    assert "No branch is deleted until its exact commit is confirmed reachable through the archive tag." in text
