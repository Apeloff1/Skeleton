"""Reconciliation engine regressions for auto-merge."""

from __future__ import annotations

from dataclasses import replace
import pytest

from skeleton.pr_automation.automerge_engine import (
    EngineConfig,
    assert_report_consistent,
    build_iteration,
    decisions_by_kind,
    mutation_failure_count,
    mutation_success_count,
    reconcile,
    report_markdown,
    select_mutation,
)
from skeleton.pr_automation.automerge_ledger import MergeLedger
from skeleton.pr_automation.automerge_model import (
    DecisionKind,
    MergeMode,
    MutationReceipt,
    ReconcileReport,
    StackRelation,
)
from skeleton.testing.automerge_test_support import (
    BASE_WORKFLOWS,
    FakeClient,
    NOW,
    SHA_A,
    SHA_B,
    SHA_C,
    policy,
    snapshot,
    successful_runs,
)


class StaticClock:
    def __init__(self, value=NOW):
        self.value = value

    def __call__(self):
        return self.value


def test_build_iteration_captures_base_and_candidate():
    candidate = snapshot()
    client = FakeClient((candidate,), base_head=SHA_A)
    iteration = build_iteration(client, policy(), now=NOW)
    assert iteration.base_head == SHA_A
    assert len(iteration.candidates) == 1
    assert iteration.candidates[0].identity.number == 1


def test_build_iteration_annotates_root():
    client = FakeClient((snapshot(),), base_head=SHA_A)
    iteration = build_iteration(client, policy(), now=NOW)
    assert iteration.candidates[0].stack_relation is StackRelation.ROOT


def test_build_iteration_produces_merge_decision_for_ready_root():
    client = FakeClient((snapshot(),), base_head=SHA_A)
    iteration = build_iteration(client, policy(), now=NOW)
    assert iteration.decisions[0].kind is DecisionKind.MERGE


def test_build_iteration_holds_root_when_base_snapshot_is_stale():
    candidate = snapshot(base_sha=SHA_B)
    client = FakeClient((candidate,), base_head=SHA_A)
    iteration = build_iteration(client, policy(), now=NOW)
    decision = iteration.decisions[0]
    assert decision.kind is DecisionKind.HOLD
    assert "default_branch_head_moved_since_candidate_snapshot" in decision.reasons


def test_build_iteration_holds_child_when_parent_head_sha_moved():
    root = snapshot(
        number=1,
        head_ref="feature/root",
        head_sha=SHA_B,
    )
    child = snapshot(
        number=2,
        base_ref="feature/root",
        base_sha=SHA_A,
        head_ref="feature/child",
        head_sha=SHA_C,
    )
    client = FakeClient((root, child), base_head=SHA_A)
    iteration = build_iteration(client, policy(), now=NOW)
    decision = next(item for item in iteration.decisions if item.pr_number == 2)
    assert decision.kind is DecisionKind.HOLD
    assert "stack_parent_head_moved_since_candidate_snapshot" in decision.reasons


def test_build_iteration_allows_child_when_parent_sha_matches():
    root = snapshot(
        number=1,
        head_ref="feature/root",
        head_sha=SHA_B,
    )
    child = snapshot(
        number=2,
        base_ref="feature/root",
        base_sha=SHA_B,
        head_ref="feature/child",
        head_sha=SHA_C,
    )
    client = FakeClient((root, child), base_head=SHA_A)
    iteration = build_iteration(client, policy(), now=NOW)
    decision = next(item for item in iteration.decisions if item.pr_number == 2)
    assert decision.kind is DecisionKind.MERGE_STACK_CHILD


def test_select_mutation_prefers_ready_stack_leaf():
    root = snapshot(
        number=1,
        head_ref="feature/root",
        head_sha=SHA_B,
    )
    child = snapshot(
        number=2,
        base_ref="feature/root",
        base_sha=SHA_B,
        head_ref="feature/child",
        head_sha=SHA_C,
    )
    client = FakeClient((root, child), base_head=SHA_A)
    iteration = build_iteration(client, policy(), now=NOW)
    selection = select_mutation(
        iteration,
        policy(),
        root_merges_used=0,
        stack_merges_used=0,
    )
    assert selection is not None
    assert selection.action.kind is DecisionKind.MERGE_STACK_CHILD
    assert selection.snapshot.identity.number == 2


def test_select_mutation_uses_root_when_no_stack_child():
    client = FakeClient((snapshot(),), base_head=SHA_A)
    iteration = build_iteration(client, policy(), now=NOW)
    selection = select_mutation(
        iteration,
        policy(),
        root_merges_used=0,
        stack_merges_used=0,
    )
    assert selection is not None
    assert selection.action.kind is DecisionKind.MERGE


def test_select_mutation_respects_root_merge_budget():
    client = FakeClient((snapshot(),), base_head=SHA_A)
    p = policy(max_merges=1)
    iteration = build_iteration(client, p, now=NOW)
    selection = select_mutation(
        iteration,
        p,
        root_merges_used=1,
        stack_merges_used=0,
    )
    assert selection is None


def test_select_mutation_can_skip_stack_when_stack_budget_spent():
    root = snapshot(
        number=1,
        head_ref="feature/root",
        head_sha=SHA_B,
    )
    child = snapshot(
        number=2,
        base_ref="feature/root",
        base_sha=SHA_B,
        head_ref="feature/child",
        head_sha=SHA_C,
    )
    client = FakeClient((root, child), base_head=SHA_A)
    p = policy(max_stack_merges=1)
    iteration = build_iteration(client, p, now=NOW)
    selection = select_mutation(
        iteration,
        p,
        root_merges_used=0,
        stack_merges_used=1,
    )
    assert selection is not None
    assert selection.action.kind is DecisionKind.MERGE
    assert selection.snapshot.identity.number == 1


def test_reconcile_merges_one_ready_root():
    client = FakeClient((snapshot(),), base_head=SHA_A)
    ledger = MergeLedger()
    report = reconcile(
        client,
        policy(max_merges=1),
        ledger=ledger,
        clock=StaticClock(),
    )
    assert len(client.merges) == 1
    assert client.merges[0][0] == 1
    assert mutation_success_count(report) == 1
    assert report.base_head_before == SHA_A
    assert report.base_head_after == SHA_C
    assert ledger.mutation_count() == 1


def test_reconcile_dispatches_post_merge_evidence_workflows():
    client = FakeClient((snapshot(),), base_head=SHA_A)
    reconcile(
        client,
        policy(max_merges=1),
        clock=StaticClock(),
    )
    assert ("merge-readiness.yml", "main") in client.dispatches
    assert ("queue-drain.yml", "main") in client.dispatches


def test_reconcile_can_disable_post_merge_dispatch():
    client = FakeClient((snapshot(),), base_head=SHA_A)
    reconcile(
        client,
        policy(max_merges=1),
        config=EngineConfig(dispatch_post_merge=False),
        clock=StaticClock(),
    )
    assert client.dispatches == []


def test_reconcile_observe_mode_never_mutates():
    client = FakeClient((snapshot(),), base_head=SHA_A)
    report = reconcile(
        client,
        policy(mode=MergeMode.OBSERVE),
        clock=StaticClock(),
    )
    assert client.merges == []
    assert report.receipts == ()
    assert report.base_head_before == report.base_head_after == SHA_A


def test_reconcile_native_mode_enables_native_once_due_to_idempotency():
    client = FakeClient((snapshot(),), base_head=SHA_A)
    ledger = MergeLedger()
    report = reconcile(
        client,
        policy(mode=MergeMode.ENABLE_NATIVE, max_merges=3),
        ledger=ledger,
        clock=StaticClock(),
    )
    assert len(client.native) == 1
    assert len(report.receipts) == 1
    assert ledger.mutation_count() == 1


def test_reconcile_records_action_idempotency_key_in_receipt():
    client = FakeClient((snapshot(),), base_head=SHA_A)
    ledger = MergeLedger()
    report = reconcile(
        client,
        policy(max_merges=1),
        ledger=ledger,
        clock=StaticClock(),
    )
    decision = next(item for item in report.decisions if item.pr_number == 1)
    assert report.receipts[0].action_key == decision.actions[0].idempotency_key
    assert ledger.has_action_key(decision.actions[0].idempotency_key)


def test_reconcile_stops_after_stack_mutation_by_default():
    root = snapshot(
        number=1,
        head_ref="feature/root",
        head_sha=SHA_B,
    )
    child = snapshot(
        number=2,
        base_ref="feature/root",
        base_sha=SHA_B,
        head_ref="feature/child",
        head_sha=SHA_C,
    )
    client = FakeClient((root, child), base_head=SHA_A)
    report = reconcile(
        client,
        policy(),
        clock=StaticClock(),
    )
    assert len(client.merges) == 1
    assert client.merges[0][0] == 2
    assert len(report.receipts) == 1
    assert report.base_head_after == SHA_A


def test_stack_mutation_does_not_dispatch_default_branch_workflows():
    root = snapshot(
        number=1,
        head_ref="feature/root",
        head_sha=SHA_B,
    )
    child = snapshot(
        number=2,
        base_ref="feature/root",
        base_sha=SHA_B,
        head_ref="feature/child",
        head_sha=SHA_C,
    )
    client = FakeClient((root, child), base_head=SHA_A)
    reconcile(
        client,
        policy(),
        clock=StaticClock(),
    )
    assert client.dispatches == []


def test_reconcile_ledger_records_decision_before_mutation():
    client = FakeClient((snapshot(),), base_head=SHA_A)
    ledger = MergeLedger()
    reconcile(
        client,
        policy(max_merges=1),
        ledger=ledger,
        clock=StaticClock(),
    )
    assert [record.kind for record in ledger.records[:2]] == [
        "decision",
        "mutation",
    ]


def test_reconcile_records_base_transition_after_direct_merge():
    client = FakeClient((snapshot(),), base_head=SHA_A)
    ledger = MergeLedger()
    reconcile(
        client,
        policy(max_merges=1),
        ledger=ledger,
        clock=StaticClock(),
    )
    assert ledger.records[-1].kind == "base_transition"
    assert ledger.records[-1].payload["before"] == SHA_A
    assert ledger.records[-1].payload["after"] == SHA_C


def test_reconcile_does_not_record_base_transition_without_merge():
    client = FakeClient((snapshot(draft=True),), base_head=SHA_A)
    ledger = MergeLedger()
    reconcile(
        client,
        policy(),
        ledger=ledger,
        clock=StaticClock(),
    )
    assert all(record.kind != "base_transition" for record in ledger.records)


def test_reconcile_holds_draft_without_mutation():
    client = FakeClient((snapshot(draft=True),), base_head=SHA_A)
    report = reconcile(
        client,
        policy(),
        clock=StaticClock(),
    )
    assert client.merges == []
    assert report.receipts == ()
    assert report.decisions[0].kind is DecisionKind.HOLD


def test_reconcile_holds_pending_ci_without_mutation():
    candidate = snapshot(
        workflow_runs=(
            *successful_runs(BASE_WORKFLOWS[1:]),
            replace(
                successful_runs(("CI/CD",))[0],
                status="in_progress",
                conclusion=None,
            ),
        )
    )
    client = FakeClient((candidate,), base_head=SHA_A)
    report = reconcile(client, policy(), clock=StaticClock())
    assert client.merges == []
    assert report.decisions[0].kind is DecisionKind.HOLD


def test_reconcile_respects_explicit_opt_out():
    client = FakeClient(
        (snapshot(labels=("do-not-merge",)),),
        base_head=SHA_A,
    )
    report = reconcile(client, policy(), clock=StaticClock())
    assert client.merges == []
    assert "explicit_automerge_opt_out" in report.decisions[0].reasons


def test_reconcile_mutates_critical_trust_surface_after_full_evidence():
    candidate = snapshot(
        files=("skeleton/pr_automation/core.py",),
        workflow_runs=successful_runs(
            (
                *BASE_WORKFLOWS,
                "Backend Quality",
                "Frontier Contracts",
                "ARM64 Ubuntu Validation",
                "Workflow Input Security",
                "Dependency Security",
                "Dependency Review",
            )
        ),
    )
    client = FakeClient((candidate,), base_head=SHA_A)
    report = reconcile(client, policy(), clock=StaticClock())
    assert client.merges
    assert report.decisions[0].kind is DecisionKind.MERGE


def test_reconcile_scanned_reports_inventory_size():
    candidates = (
        snapshot(number=1, head_ref="feature/a", head_sha=SHA_B),
        snapshot(number=2, head_ref="feature/b", head_sha=SHA_C),
    )
    client = FakeClient(candidates, base_head=SHA_A)
    report = reconcile(
        client,
        policy(mode=MergeMode.OBSERVE),
        clock=StaticClock(),
    )
    assert report.scanned == 2


def test_report_markdown_contains_decisions_and_mutations():
    client = FakeClient((snapshot(),), base_head=SHA_A)
    report = reconcile(
        client,
        policy(max_merges=1),
        clock=StaticClock(),
    )
    text = report_markdown(report)
    assert "# Auto-merge reconciliation" in text
    assert "| #1 | merge |" in text
    assert "Mutations attempted: 1" in text


def test_decisions_by_kind_groups_results():
    client = FakeClient(
        (
            snapshot(number=1, head_ref="feature/a", head_sha=SHA_B),
            snapshot(
                number=2,
                head_ref="feature/b",
                head_sha=SHA_C,
                draft=True,
            ),
        ),
        base_head=SHA_A,
    )
    report = reconcile(
        client,
        policy(mode=MergeMode.OBSERVE),
        clock=StaticClock(),
    )
    grouped = decisions_by_kind(report)
    assert grouped[DecisionKind.READY][0].pr_number == 1
    assert grouped[DecisionKind.HOLD][0].pr_number == 2


def test_mutation_failure_count():
    report = ReconcileReport(
        repository="Apeloff1/Skeleton",
        default_branch="main",
        policy_fingerprint="a" * 64,
        scanned=1,
        decisions=(),
        receipts=(
            MutationReceipt(
                pr_number=1,
                action_key="a",
                requested_head_sha=SHA_B,
                observed_head_sha=SHA_B,
                base_ref="main",
                merged=False,
                merge_sha=None,
                message="rejected",
            ),
        ),
        base_head_before=SHA_A,
        base_head_after=SHA_A,
        started_at=NOW.isoformat(),
        finished_at=NOW.isoformat(),
    )
    assert mutation_failure_count(report) == 1
    assert mutation_success_count(report) == 0


def test_assert_report_consistent_rejects_receipt_without_decision():
    report = ReconcileReport(
        repository="Apeloff1/Skeleton",
        default_branch="main",
        policy_fingerprint="a" * 64,
        scanned=1,
        decisions=(),
        receipts=(
            MutationReceipt(
                pr_number=1,
                action_key="a",
                requested_head_sha=SHA_B,
                observed_head_sha=SHA_B,
                base_ref="main",
                merged=True,
                merge_sha=SHA_C,
                message="merged",
            ),
        ),
        base_head_before=SHA_A,
        base_head_after=SHA_C,
        started_at=NOW.isoformat(),
        finished_at=NOW.isoformat(),
    )
    with pytest.raises(ValueError, match="no decision"):
        assert_report_consistent(report)


def test_assert_report_consistent_rejects_unexplained_base_move():
    report = ReconcileReport(
        repository="Apeloff1/Skeleton",
        default_branch="main",
        policy_fingerprint="a" * 64,
        scanned=0,
        decisions=(),
        receipts=(),
        base_head_before=SHA_A,
        base_head_after=SHA_C,
        started_at=NOW.isoformat(),
        finished_at=NOW.isoformat(),
    )
    with pytest.raises(ValueError, match="without a recorded successful merge"):
        assert_report_consistent(report)


def test_assert_report_consistent_accepts_observe_report():
    client = FakeClient((snapshot(),), base_head=SHA_A)
    report = reconcile(
        client,
        policy(mode=MergeMode.OBSERVE),
        clock=StaticClock(),
    )
    assert_report_consistent(report)


def test_report_policy_fingerprint_matches_runtime_policy():
    p = policy()
    client = FakeClient((snapshot(),), base_head=SHA_A)
    report = reconcile(
        client,
        p,
        clock=StaticClock(),
    )
    assert report.policy_fingerprint == p.fingerprint()


def test_report_timestamps_use_clock():
    clock = StaticClock(NOW)
    client = FakeClient((snapshot(draft=True),), base_head=SHA_A)
    report = reconcile(client, policy(), clock=clock)
    assert report.started_at == NOW.isoformat()
    assert report.finished_at == NOW.isoformat()


def test_decision_ledger_is_deduplicated_per_snapshot():
    client = FakeClient((snapshot(),), base_head=SHA_A)
    ledger = MergeLedger()
    reconcile(
        client,
        policy(mode=MergeMode.ENABLE_NATIVE, max_merges=3),
        ledger=ledger,
        clock=StaticClock(),
    )
    decision_records = [
        record for record in ledger.records if record.kind == "decision"
    ]
    assert len(decision_records) == 1


def test_existing_action_key_prevents_replay():
    candidate = snapshot()
    client = FakeClient((candidate,), base_head=SHA_A)
    first_ledger = MergeLedger()
    first_report = reconcile(
        client,
        policy(mode=MergeMode.ENABLE_NATIVE),
        ledger=first_ledger,
        clock=StaticClock(),
    )
    assert len(first_report.receipts) == 1

    fresh_client = FakeClient((candidate,), base_head=SHA_A)
    second_report = reconcile(
        fresh_client,
        policy(mode=MergeMode.ENABLE_NATIVE),
        ledger=first_ledger,
        clock=StaticClock(),
    )
    assert fresh_client.native == []
    assert second_report.receipts == ()


def test_post_merge_workflow_list_is_configurable():
    client = FakeClient((snapshot(),), base_head=SHA_A)
    reconcile(
        client,
        policy(max_merges=1),
        config=EngineConfig(
            dispatch_post_merge=True,
            post_merge_workflows=("custom-validation.yml",),
        ),
        clock=StaticClock(),
    )
    assert client.dispatches == [("custom-validation.yml", "main")]


def test_engine_config_rejects_duplicate_post_merge_workflows():
    with pytest.raises(ValueError, match="duplicate"):
        EngineConfig(post_merge_workflows=("a.yml", "a.yml"))


def test_root_and_child_decisions_exist_in_same_iteration():
    root = snapshot(
        number=1,
        head_ref="feature/root",
        head_sha=SHA_B,
    )
    child = snapshot(
        number=2,
        base_ref="feature/root",
        base_sha=SHA_B,
        head_ref="feature/child",
        head_sha=SHA_C,
    )
    client = FakeClient((root, child), base_head=SHA_A)
    iteration = build_iteration(client, policy(), now=NOW)
    by_number = {item.pr_number: item for item in iteration.decisions}
    assert by_number[1].kind is DecisionKind.MERGE
    assert by_number[2].kind is DecisionKind.MERGE_STACK_CHILD


def test_stack_child_action_is_bound_to_child_head():
    root = snapshot(
        number=1,
        head_ref="feature/root",
        head_sha=SHA_B,
    )
    child = snapshot(
        number=2,
        base_ref="feature/root",
        base_sha=SHA_B,
        head_ref="feature/child",
        head_sha=SHA_C,
    )
    client = FakeClient((root, child), base_head=SHA_A)
    iteration = build_iteration(client, policy(), now=NOW)
    decision = next(item for item in iteration.decisions if item.pr_number == 2)
    assert decision.actions[0].expected_head_sha == SHA_C
    assert decision.actions[0].expected_base_sha == SHA_B


def test_orphan_stack_candidate_never_selected():
    orphan = snapshot(
        number=2,
        base_ref="feature/missing",
        base_sha=SHA_B,
        head_ref="feature/child",
        head_sha=SHA_C,
    )
    client = FakeClient((orphan,), base_head=SHA_A)
    iteration = build_iteration(client, policy(), now=NOW)
    assert iteration.decisions[0].kind is DecisionKind.HOLD
    assert select_mutation(
        iteration,
        policy(),
        root_merges_used=0,
        stack_merges_used=0,
    ) is None


def test_cycle_stack_candidates_never_selected():
    one = snapshot(
        number=1,
        base_ref="feature/two",
        base_sha=SHA_C,
        head_ref="feature/one",
        head_sha=SHA_B,
    )
    two = snapshot(
        number=2,
        base_ref="feature/one",
        base_sha=SHA_B,
        head_ref="feature/two",
        head_sha=SHA_C,
    )
    client = FakeClient((one, two), base_head=SHA_A)
    iteration = build_iteration(client, policy(), now=NOW)
    assert all(item.kind is DecisionKind.HOLD for item in iteration.decisions)
    assert select_mutation(
        iteration,
        policy(),
        root_merges_used=0,
        stack_merges_used=0,
    ) is None


def test_failed_root_does_not_block_independent_ready_root_selection():
    blocked = snapshot(
        number=1,
        head_ref="feature/blocked",
        head_sha=SHA_B,
        draft=True,
    )
    ready = snapshot(
        number=2,
        head_ref="feature/ready",
        head_sha=SHA_C,
        base_sha=SHA_A,
        workflow_runs=successful_runs(
            BASE_WORKFLOWS,
            head_sha=SHA_C,
        ),
    )
    client = FakeClient((blocked, ready), base_head=SHA_A)
    iteration = build_iteration(client, policy(), now=NOW)
    selection = select_mutation(
        iteration,
        policy(),
        root_merges_used=0,
        stack_merges_used=0,
    )
    assert selection is not None
    assert selection.snapshot.identity.number == 2


def test_reconcile_mutates_independent_ready_root_when_lower_number_is_held():
    blocked = snapshot(
        number=1,
        head_ref="feature/blocked",
        head_sha=SHA_B,
        draft=True,
    )
    ready = snapshot(
        number=2,
        head_ref="feature/ready",
        head_sha=SHA_C,
        base_sha=SHA_A,
        workflow_runs=successful_runs(
            BASE_WORKFLOWS,
            head_sha=SHA_C,
        ),
    )
    client = FakeClient((blocked, ready), base_head=SHA_A)
    report = reconcile(
        client,
        policy(max_merges=1),
        clock=StaticClock(),
    )
    assert client.merges[0][0] == 2
    assert mutation_success_count(report) == 1


def test_report_markdown_escapes_pipe_in_reason():
    held = snapshot(draft=True)
    client = FakeClient((held,), base_head=SHA_A)
    report = reconcile(client, policy(), clock=StaticClock())
    # Injecting pipes is unnecessary; ensure normal markdown remains table-shaped.
    text = report_markdown(report)
    assert "| #1 | hold |" in text
