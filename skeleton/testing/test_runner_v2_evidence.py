"""Evidence normalization and collection regressions for runner v2."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from skeleton.pr_automation.core import CIState
from skeleton.pr_automation.runner_contracts import CheckState
from skeleton.pr_automation.runner_evidence import (
    EvidenceCollector,
    EvidenceError,
    aggregate_ci_state,
    approval_count,
    change_request_count,
    check_state_map,
    failing_required_checks,
    latest_decisive_reviews,
    missing_required_checks,
    newest_provider_evidence,
    normalize_check_run,
    normalize_file,
    normalize_review,
    normalize_status,
    pending_required_checks,
    reduce_context_state,
    required_check_states,
    sensitive_paths,
    snapshot_incomplete_reasons,
    stale_reviewers,
)
from skeleton.testing.runner_v2_test_support import (
    BASE_CHECKS,
    NOW,
    SHA_A,
    SHA_B,
    SHA_C,
    ScriptedTransport,
    branch_payload,
    check,
    check_run_payload,
    configure_collector_transport,
    file_payload,
    pr_payload,
    review,
    review_payload,
    runner_policy,
    snapshot,
    status_payload,
    threads_payload,
)


@pytest.mark.parametrize(
    "status,conclusion,expected",
    [
        ("completed", "success", CheckState.PASSING),
        ("completed", "failure", CheckState.FAILING),
        ("completed", "cancelled", CheckState.CANCELLED),
        ("completed", "skipped", CheckState.SKIPPED),
        ("completed", "neutral", CheckState.UNKNOWN),
        ("queued", None, CheckState.PENDING),
        ("in_progress", None, CheckState.PENDING),
    ],
)
def test_normalize_check_run_state_mapping(status, conclusion, expected):
    payload = check_run_payload(
        "CI/CD",
        status=status,
        state=conclusion,
    )
    item = normalize_check_run(payload, expected_head_sha=SHA_B)
    assert item is not None
    assert item.state is expected


def test_normalize_check_run_rejects_other_head():
    item = normalize_check_run(
        check_run_payload("CI/CD", head_sha=SHA_A),
        expected_head_sha=SHA_B,
    )
    assert item is None


def test_normalize_check_run_requires_name():
    payload = check_run_payload("CI/CD")
    payload["name"] = ""
    assert normalize_check_run(payload, expected_head_sha=SHA_B) is None


@pytest.mark.parametrize(
    "state,expected",
    [
        ("success", CheckState.PASSING),
        ("failure", CheckState.FAILING),
        ("error", CheckState.FAILING),
        ("pending", CheckState.PENDING),
        ("unknown", CheckState.UNKNOWN),
    ],
)
def test_normalize_status_state_mapping(state, expected):
    item = normalize_status(
        status_payload("CI/CD", state=state),
        expected_head_sha=SHA_B,
    )
    assert item is not None
    assert item.state is expected


def test_normalize_status_ignores_runner_gate():
    assert normalize_status(
        status_payload("PR Automation Gate"),
        expected_head_sha=SHA_B,
    ) is None


def test_newest_provider_evidence_selects_latest():
    old = check(
        "CI/CD",
        state=CheckState.PASSING,
        source_id=1,
        updated_at=NOW - timedelta(minutes=20),
    )
    new = check(
        "CI/CD",
        state=CheckState.FAILING,
        source_id=2,
        updated_at=NOW - timedelta(minutes=1),
    )
    current = newest_provider_evidence((old, new))
    assert len(current) == 1
    assert current[0].state is CheckState.FAILING


def test_newest_provider_evidence_keeps_distinct_providers():
    one = check("CI/CD", provider="one", source_id=1)
    two = check("CI/CD", provider="two", source_id=2)
    assert len(newest_provider_evidence((one, two))) == 2


@pytest.mark.parametrize(
    "states,expected",
    [
        ((CheckState.PASSING,), CheckState.PASSING),
        ((CheckState.PASSING, CheckState.PENDING), CheckState.PENDING),
        ((CheckState.PASSING, CheckState.FAILING), CheckState.FAILING),
        ((CheckState.PASSING, CheckState.CANCELLED), CheckState.FAILING),
        ((CheckState.PASSING, CheckState.UNKNOWN), CheckState.UNKNOWN),
        ((CheckState.PASSING, CheckState.SKIPPED), CheckState.UNKNOWN),
    ],
)
def test_reduce_context_state_is_fail_closed(states, expected):
    items = tuple(
        check(
            "CI/CD",
            state=state,
            provider=f"provider-{index}",
            source_id=index + 1,
        )
        for index, state in enumerate(states)
    )
    assert reduce_context_state(items, context="CI/CD") is expected


def test_reduce_context_state_missing():
    assert reduce_context_state((), context="CI/CD") is CheckState.MISSING


def test_required_check_states_preserves_order():
    evidence = (
        check("A", source_id=1),
        check("B", source_id=2),
    )
    result = required_check_states(evidence, ("B", "A", "C"))
    assert result == (
        ("B", CheckState.PASSING),
        ("A", CheckState.PASSING),
        ("C", CheckState.MISSING),
    )


def test_aggregate_ci_requires_all_named_checks():
    evidence = (check("A"),)
    assert aggregate_ci_state(evidence, ("A", "B")) is CIState.MISSING


def test_aggregate_ci_failure_overrides_success():
    evidence = (
        check("A", state=CheckState.PASSING),
        check("B", state=CheckState.FAILING, source_id=2),
    )
    assert aggregate_ci_state(evidence, ("A", "B")) is CIState.FAILING


def test_normalize_review_casefolds_login():
    item = normalize_review(
        review_payload(login="ReviewER")
    )
    assert item is not None
    assert item.login == "reviewer"


def test_normalize_review_rejects_bad_commit():
    payload = review_payload()
    payload["commit_id"] = "bad"
    assert normalize_review(payload) is None


def test_latest_decisive_reviews_ignores_comments():
    approved = review("alice", state="APPROVED", review_id=1)
    commented = review(
        "alice",
        state="COMMENTED",
        review_id=2,
        submitted_at=NOW,
    )
    latest = latest_decisive_reviews((approved, commented))
    assert latest == (approved,)


def test_latest_decisive_reviews_new_change_request_wins():
    approved = review(
        "alice",
        state="APPROVED",
        review_id=1,
        submitted_at=NOW - timedelta(minutes=5),
    )
    changes = review(
        "alice",
        state="CHANGES_REQUESTED",
        review_id=2,
        submitted_at=NOW,
    )
    latest = latest_decisive_reviews((approved, changes))
    assert latest[0].state == "CHANGES_REQUESTED"


def test_approval_count_can_require_exact_head():
    items = (
        review("alice", commit_id=SHA_A),
        review("bob", review_id=2, commit_id=SHA_B),
    )
    assert approval_count(
        items,
        head_sha=SHA_B,
        require_head_match=True,
    ) == 1
    assert approval_count(
        items,
        head_sha=SHA_B,
        require_head_match=False,
    ) == 2


def test_change_request_count_uses_latest_decisive_state():
    items = (
        review("alice", state="APPROVED", review_id=1),
        review(
            "alice",
            state="CHANGES_REQUESTED",
            review_id=2,
            submitted_at=NOW,
        ),
    )
    assert change_request_count(items) == 1


def test_normalize_file():
    item = normalize_file(
        file_payload("src/a.py", additions=7, deletions=2)
    )
    assert item.filename == "src/a.py"
    assert item.changes == 9


def test_normalize_file_requires_filename():
    with pytest.raises(EvidenceError):
        normalize_file({"filename": ""})


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        ".github/actions/x/action.yml",
        "skeleton/pr_automation/runner.py",
        "security/policy.py",
        "scripts/check_automerge_contract.py",
    ],
)
def test_sensitive_paths_detects_trust_surface(path):
    item = normalize_file(file_payload(path))
    assert path in sensitive_paths((item,))


def test_sensitive_paths_detects_previous_name():
    item = normalize_file(
        file_payload(
            "docs/moved.md",
            status="renamed",
            previous_filename=".github/workflows/old.yml",
        )
    )
    assert ".github/workflows/old.yml" in sensitive_paths((item,))


def test_collector_builds_complete_snapshot():
    transport = configure_collector_transport(
        ScriptedTransport(),
        reviews=(review_payload(login="alice"),),
    )
    collector = EvidenceCollector(transport, runner_policy())
    result = collector.collect("Apeloff1/Skeleton", 42)
    assert result.completeness.complete
    assert result.core.ci_state is CIState.PASSING
    assert result.core.approvals == 1
    assert result.core.changes_requested == 0
    assert result.core.unresolved_threads == 0
    assert result.same_repository_head
    assert result.exact_base_head


def test_collector_detects_fork():
    transport = configure_collector_transport(
        ScriptedTransport(),
        pr=pr_payload(head_repo="fork/Skeleton"),
    )
    result = EvidenceCollector(
        transport,
        runner_policy(),
    ).collect("Apeloff1/Skeleton", 42)
    assert result.core.from_fork
    assert not result.same_repository_head


def test_collector_exact_head_approval_requirement():
    transport = configure_collector_transport(
        ScriptedTransport(),
        reviews=(
            review_payload(login="alice", commit_id=SHA_A),
            review_payload(login="bob", review_id=2, commit_id=SHA_B),
        ),
    )
    result = EvidenceCollector(
        transport,
        runner_policy(),
    ).collect("Apeloff1/Skeleton", 42)
    assert result.core.approvals == 1


def test_collector_counts_change_requests():
    transport = configure_collector_transport(
        ScriptedTransport(),
        reviews=(
            review_payload(
                login="alice",
                state="CHANGES_REQUESTED",
            ),
        ),
    )
    result = EvidenceCollector(
        transport,
        runner_policy(),
    ).collect("Apeloff1/Skeleton", 42)
    assert result.core.changes_requested == 1


def test_collector_counts_unresolved_threads():
    transport = configure_collector_transport(ScriptedTransport())
    transport.graphql_queue[:] = [threads_payload(unresolved=3)]
    result = EvidenceCollector(
        transport,
        runner_policy(),
    ).collect("Apeloff1/Skeleton", 42)
    assert result.core.unresolved_threads == 3


def test_collector_paginates_review_threads():
    transport = configure_collector_transport(ScriptedTransport())
    transport.graphql_queue[:] = [
        threads_payload(unresolved=1, has_next=True, cursor="next"),
        threads_payload(unresolved=2, has_next=False),
    ]
    result = EvidenceCollector(
        transport,
        runner_policy(),
    ).collect("Apeloff1/Skeleton", 42)
    assert result.core.unresolved_threads == 3


def test_collector_marks_threads_incomplete_when_cursor_missing():
    transport = configure_collector_transport(ScriptedTransport())
    transport.graphql_queue[:] = [
        threads_payload(unresolved=1, has_next=True, cursor=None)
    ]
    result = EvidenceCollector(
        transport,
        runner_policy(),
    ).collect("Apeloff1/Skeleton", 42)
    assert result.core.unresolved_threads is None
    assert not result.completeness.threads


def test_collector_marks_files_incomplete_on_count_mismatch():
    transport = configure_collector_transport(
        ScriptedTransport(),
        pr=pr_payload(changed_files=2),
        files=(file_payload("a.py"),),
    )
    result = EvidenceCollector(
        transport,
        runner_policy(),
    ).collect("Apeloff1/Skeleton", 42)
    assert not result.completeness.files
    assert result.core.sensitive_paths is None


def test_collector_uses_pr_summary_line_counts():
    transport = configure_collector_transport(
        ScriptedTransport(),
        pr=pr_payload(additions=100, deletions=50),
        files=(file_payload(additions=1, deletions=1),),
    )
    result = EvidenceCollector(
        transport,
        runner_policy(),
    ).collect("Apeloff1/Skeleton", 42)
    assert result.core.additions == 100
    assert result.core.deletions == 50


def test_collector_marks_failed_check():
    transport = configure_collector_transport(
        ScriptedTransport(),
        checks=(
            check_run_payload("Merge Readiness"),
            check_run_payload(
                "CI/CD",
                state="failure",
                run_id=2,
            ),
        ),
    )
    result = EvidenceCollector(
        transport,
        runner_policy(),
    ).collect("Apeloff1/Skeleton", 42)
    assert result.core.ci_state is CIState.FAILING
    assert failing_required_checks(result) == ("CI/CD",)


def test_collector_marks_pending_check():
    transport = configure_collector_transport(
        ScriptedTransport(),
        checks=(
            check_run_payload("Merge Readiness"),
            check_run_payload(
                "CI/CD",
                status="in_progress",
                state=None,
                run_id=2,
            ),
        ),
    )
    result = EvidenceCollector(
        transport,
        runner_policy(),
    ).collect("Apeloff1/Skeleton", 42)
    assert result.core.ci_state is CIState.PENDING
    assert pending_required_checks(result) == ("CI/CD",)


def test_collector_marks_missing_check():
    transport = configure_collector_transport(
        ScriptedTransport(),
        checks=(check_run_payload("Merge Readiness"),),
    )
    result = EvidenceCollector(
        transport,
        runner_policy(),
    ).collect("Apeloff1/Skeleton", 42)
    assert result.core.ci_state is CIState.MISSING
    assert missing_required_checks(result) == ("CI/CD",)


def test_collector_marks_base_head_move():
    transport = configure_collector_transport(
        ScriptedTransport(),
        base=branch_payload(sha=SHA_C),
    )
    result = EvidenceCollector(
        transport,
        runner_policy(),
    ).collect("Apeloff1/Skeleton", 42)
    assert not result.exact_base_head
    assert result.base_head_sha == SHA_C


def test_collector_rejects_invalid_pr_head_sha():
    transport = configure_collector_transport(
        ScriptedTransport(),
        pr=pr_payload(head_sha="bad"),
    )
    collector = EvidenceCollector(transport, runner_policy())
    with pytest.raises(EvidenceError, match="head SHA"):
        collector.collect("Apeloff1/Skeleton", 42)


def test_snapshot_incomplete_reasons():
    snap = replace(
        snapshot(),
        completeness=replace(
            snapshot().completeness,
            reviews=False,
            threads=False,
        ),
    )
    assert snapshot_incomplete_reasons(snap) == (
        "evidence_incomplete:reviews",
        "evidence_incomplete:threads",
    )


def test_check_state_map():
    assert check_state_map(snapshot()) == {
        "Merge Readiness": CheckState.PASSING,
        "CI/CD": CheckState.PASSING,
    }


def test_stale_reviewers():
    snap = replace(
        snapshot(),
        reviews=(
            review("alice", commit_id=SHA_A),
            review("bob", review_id=2, commit_id=SHA_B),
        ),
    )
    assert stale_reviewers(snap) == ("alice",)
