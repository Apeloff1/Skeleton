from __future__ import annotations

from pathlib import Path

from scripts.check_repo_attention_contract import violations_for_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "repo-attention.yml"


def _source() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _replace_once(source: str, old: str, new: str) -> str:
    assert old in source, f"fixture marker missing: {old!r}"
    return source.replace(old, new, 1)


def _messages(source: str) -> str:
    return "\n".join(violations_for_text(source))


def test_live_repository_attention_contract_passes() -> None:
    assert violations_for_text(_source()) == []


def test_rejects_pull_request_target_regression() -> None:
    source = _replace_once(_source(), "  pull_request:\n", "  pull_request_target:\n")
    assert "pull_request_target is forbidden" in _messages(source)


def test_rejects_global_cancellation_that_can_starve_trusted_clear() -> None:
    source = _replace_once(
        _source(),
        "  cancel-in-progress: ${{ github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == github.repository }}",
        "  cancel-in-progress: true",
    )
    assert "only trusted same-repository PR lifecycle events may cancel" in _messages(source)


def test_rejects_pr_cancellation_without_same_repository_guard() -> None:
    source = _replace_once(
        _source(),
        "  cancel-in-progress: ${{ github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == github.repository }}",
        "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
    )
    assert "only trusted same-repository PR lifecycle events may cancel" in _messages(source)


def test_rejects_loss_of_same_repository_pr_guard() -> None:
    source = _replace_once(
        _source(),
        "  clear-pr-attention:\n"
        "    name: Clear attention after PR lifecycle activity\n"
        "    if: >-\n"
        "      github.event_name == 'pull_request' &&\n"
        "      github.event.pull_request.head.repo.full_name == github.repository &&\n",
        "  clear-pr-attention:\n"
        "    name: Clear attention after PR lifecycle activity\n"
        "    if: >-\n"
        "      github.event_name == 'pull_request' &&\n"
        "      true &&\n",
    )
    assert "PR label mutation must be restricted to same-repository heads" in _messages(source)


def test_rejects_broad_write_scope() -> None:
    source = _replace_once(_source(), "      issues: write\n", "      contents: write\n")
    assert "unexpected write permission scope: contents: write" in _messages(source)


def test_rejects_action_or_checkout_execution() -> None:
    source = _replace_once(
        _source(),
        "    steps:\n      - name: Ensure managed attention labels exist\n",
        "    steps:\n      - uses: actions/checkout@0000000000000000000000000000000000000000\n      - name: Ensure managed attention labels exist\n",
    )
    assert "must remain metadata/API-only" in _messages(source)


def test_rejects_blanket_api_failure_suppression() -> None:
    source = _replace_once(
        _source(),
        "          remove_label 'stale-draft'\n",
        "          remove_label 'stale-draft' || true\n",
    )
    assert "blanket || true error suppression is forbidden" in _messages(source)


def test_rejects_generic_updated_at_inactivity_clock() -> None:
    source = _replace_once(
        _source(),
        "              activity_epoch=$(date -u -d \"$activity\" +%s)\n",
        "              updated_epoch=$(date -u -d \"$activity\" +%s)\n",
    )
    assert "generic updated_at must not be used as the inactivity clock" in _messages(source)


def test_rejects_loss_of_timeline_reconciliation() -> None:
    source = _replace_once(_source(), "/timeline?per_page=100", "/events?per_page=100")
    assert "sweep contract missing timeline activity clock" in _messages(source)


def test_rejects_loss_of_commit_timestamp_extraction() -> None:
    source = _replace_once(
        _source(),
        "$e.committer.date // $e.author.date //\n                     $e.updated_at",
        "$e.updated_at",
    )
    assert "sweep contract missing commit timestamp extraction" in _messages(source)


def test_rejects_loss_of_two_pass_race_convergence() -> None:
    source = _replace_once(_source(), "            for pass in 1 2; do", "            for pass in 1; do")
    assert "sweep contract missing two-pass convergence" in _messages(source)


def test_rejects_untrusted_comment_clearing() -> None:
    source = _replace_once(
        _source(),
        "       github.event.comment.author_association == 'COLLABORATOR')",
        "       github.event.comment.author_association == 'CONTRIBUTOR')",
    )
    assert "comment-driven clearing must retain trusted association: COLLABORATOR" in _messages(source)


def test_rejects_loss_of_review_comment_event_coverage() -> None:
    source = _replace_once(
        _source(),
        "  pull_request_review_comment:\n    types: [created, edited]\n",
        "",
    )
    assert "pull_request_review_comment trigger is missing activity type" in _messages(source)


def test_rejects_merge_queue_state_churn() -> None:
    for event in ("enqueued", "dequeued"):
        source = _replace_once(
            _source(),
            "      - auto_merge_disabled\n",
            f"      - auto_merge_disabled\n      - {event}\n",
        )
        assert f"merge-queue state churn: {event}" in _messages(source)


def test_repository_attention_uses_general_runner_capacity() -> None:
    source = _source()

    assert source.count("runs-on: ubuntu-latest") == 5
    assert "runs-on: ubuntu-24.04-arm" not in source


def test_managed_label_presence_guards_skip_empty_clear_jobs() -> None:
    source = _source()

    required = (
        "contains(github.event.pull_request.labels.*.name, 'needs-attention')",
        "contains(github.event.pull_request.labels.*.name, 'stale-draft')",
        "contains(github.event.issue.labels.*.name, 'needs-attention')",
        "contains(github.event.issue.labels.*.name, 'stale-draft')",
    )
    for marker in required:
        assert marker in source


def test_rejects_loss_of_pr_label_presence_guard() -> None:
    source = _replace_once(
        _source(),
        "      (contains(github.event.pull_request.labels.*.name, 'needs-attention') ||\n"
        "       contains(github.event.pull_request.labels.*.name, 'stale-draft'))\n",
        "      true\n",
    )
    messages = _messages(source)
    assert "PR clear job must skip runner allocation without managed label" in messages


def test_rejects_loss_of_comment_label_presence_guard() -> None:
    source = _replace_once(
        _source(),
        "      (contains(github.event.issue.labels.*.name, 'needs-attention') ||\n"
        "       contains(github.event.issue.labels.*.name, 'stale-draft'))\n",
        "      true\n",
    )
    messages = _messages(source)
    assert "comment clear job must skip runner allocation without managed label" in messages
