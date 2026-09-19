"""Mutation-boundary, reporting, CLI, and static-contract regressions."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json

import pytest

from scripts.check_runner_v2_contract import (
    MODULES,
    PACKAGE,
    ROOT,
    WORKFLOW,
    _cross_file_findings,
    _legacy_findings,
    _module_findings,
    _workflow_findings,
    check as check_runner_contract,
)
from skeleton.pr_automation.core import Decision
from skeleton.pr_automation.index import EventIndex
from skeleton.pr_automation.runner_contracts import (
    MutationIntent,
    MutationState,
    Preconditions,
    RunnerReport,
    TargetResult,
    TargetSet,
    TransportSummary,
    WorkState,
)
from skeleton.pr_automation.runner_report import (
    append_step_summary,
    applied_merge_shas,
    assert_report_invariants,
    checkpoint_compatible,
    checkpoint_from_report,
    compact_report,
    deferred_results,
    failed_results,
    load_checkpoint,
    markdown_summary,
    mutation_counts,
    ready_without_mutation,
    report_exit_code,
    report_invariants,
    result_counts,
    save_checkpoint,
    write_report_json,
)
from skeleton.pr_automation.runner_scheduler import observe_queue
from skeleton.pr_automation.runner_transaction import (
    MergeTransaction,
    append_receipt_event,
    compute_preconditions,
    compute_transaction_preconditions,
    mutation_retriable,
    transaction_diagnostics,
)
from skeleton.pr_automation.runner_v2_cli import (
    core_policy_from_env,
    csv,
    env_bool,
    env_int,
    limits_from_env,
    runner_policy_from_env,
)
from skeleton.testing.runner_v2_test_support import (
    NOW,
    SHA_A,
    SHA_B,
    SHA_C,
    ScriptedTransport,
    admission,
    branch_payload,
    configure_collector_transport,
    identity,
    runner_policy,
    snapshot,
    work_item,
)


def all_true_preconditions() -> Preconditions:
    return Preconditions(
        protected_base=True,
        base_head_matches=True,
        head_matches=True,
        snapshot_matches=True,
        policy_matches=True,
        checks_still_passing=True,
        reviews_still_valid=True,
        queue_within_limit=True,
        rate_limit_safe=True,
    )


def make_report(*results: TargetResult) -> RunnerReport:
    targets = TargetSet(
        repository="Apeloff1/Skeleton",
        targets=tuple(
            result_to_target(result)
            for result in results
        ),
        complete=True,
        reason="test",
        requests_used=1,
    )
    attempted = sum(len(result.mutations) for result in results)
    applied = sum(
        receipt.state is MutationState.APPLIED
        for result in results
        for receipt in result.mutations
    )
    failures = sum(
        result.state is WorkState.FAILED or result.error is not None
        for result in results
    )
    deferred = sum(
        result.state is WorkState.DEFERRED
        for result in results
    )
    return RunnerReport(
        identity=identity(),
        admission=admission(),
        policy_fingerprint=runner_policy().fingerprint(),
        started_at=NOW.isoformat(),
        finished_at=(NOW + timedelta(seconds=1)).isoformat(),
        targets=targets,
        results=tuple(results),
        transport=TransportSummary(
            requests=10,
            graphql_requests=1,
            retries=0,
            bytes_received=1000,
            rate_limited=0,
            failures=0,
            minimum_remaining_seen=4990,
        ),
        mutations_attempted=attempted,
        mutations_applied=applied,
        failures=failures,
        deferred=deferred,
        final_queue_depth=0,
        final_rate_remaining=4990,
    )


def result_to_target(result: TargetResult):
    from skeleton.pr_automation.runner_contracts import PriorityBand, Target

    return Target(
        number=result.number,
        reason="test",
        priority=PriorityBand.INTERACTIVE,
    )


def simple_result(
    *,
    number: int = 42,
    state: WorkState = WorkState.READY,
    decision: Decision = Decision.READY,
    mutations=(),
    error: str | None = None,
) -> TargetResult:
    return TargetResult(
        number=number,
        state=state,
        decision=decision,
        reasons=("test",),
        snapshot_fingerprint="x" * 64,
        mutations=tuple(mutations),
        request_count=3,
        duration_ms=25,
        error=error,
    )


def test_compute_preconditions_all_true():
    snap = snapshot()
    value = compute_preconditions(
        original=snap,
        current=snap,
        policy=runner_policy(),
        protected=True,
        observed_base_head=SHA_A,
        observation=observe_queue(
            queued_actions=0,
            rate_remaining=5000,
            now=NOW,
        ),
    )
    assert value.satisfied


def test_compute_preconditions_detects_unprotected_base():
    snap = snapshot()
    value = compute_preconditions(
        original=snap,
        current=snap,
        policy=runner_policy(),
        protected=False,
        observed_base_head=SHA_A,
        observation=observe_queue(
            queued_actions=0,
            rate_remaining=5000,
            now=NOW,
        ),
    )
    assert "protected_base" in value.failed()


def test_compute_preconditions_detects_base_move():
    snap = snapshot()
    value = compute_preconditions(
        original=snap,
        current=snap,
        policy=runner_policy(),
        protected=True,
        observed_base_head=SHA_C,
        observation=observe_queue(
            queued_actions=0,
            rate_remaining=5000,
            now=NOW,
        ),
    )
    assert "base_head_matches" in value.failed()


def test_compute_preconditions_detects_head_move():
    original = snapshot()
    current = replace(
        original,
        core=replace(original.core, head_sha=SHA_C),
    )
    value = compute_preconditions(
        original=original,
        current=current,
        policy=runner_policy(),
        protected=True,
        observed_base_head=SHA_A,
        observation=observe_queue(
            queued_actions=0,
            rate_remaining=5000,
            now=NOW,
        ),
    )
    assert "head_matches" in value.failed()
    assert "snapshot_matches" in value.failed()


def test_compute_preconditions_detects_queue_pressure():
    snap = snapshot()
    value = compute_preconditions(
        original=snap,
        current=snap,
        policy=runner_policy(),
        protected=True,
        observed_base_head=SHA_A,
        observation=observe_queue(
            queued_actions=999,
            rate_remaining=5000,
            now=NOW,
        ),
    )
    assert "queue_within_limit" in value.failed()


def test_compute_preconditions_detects_low_rate_limit():
    snap = snapshot()
    value = compute_preconditions(
        original=snap,
        current=snap,
        policy=runner_policy(),
        protected=True,
        observed_base_head=SHA_A,
        observation=observe_queue(
            queued_actions=0,
            rate_remaining=1,
            now=NOW,
        ),
    )
    assert "rate_limit_safe" in value.failed()


def test_transaction_preconditions_bind_policy_and_snapshot():
    item = work_item()
    policy = runner_policy()
    intent = MutationIntent.from_work_item(item, policy)
    value = compute_transaction_preconditions(
        intent=intent,
        original=item.snapshot,
        current=item.snapshot,
        policy=policy,
        protected=True,
        observed_base_head=SHA_A,
        observation=observe_queue(
            queued_actions=0,
            rate_remaining=5000,
            now=NOW,
        ),
    )
    assert value.satisfied


def test_transaction_preconditions_reject_policy_change():
    item = work_item()
    policy = runner_policy()
    intent = MutationIntent.from_work_item(item, policy)
    changed = replace(policy, merge_method="merge")
    value = compute_transaction_preconditions(
        intent=intent,
        original=item.snapshot,
        current=item.snapshot,
        policy=changed,
        protected=True,
        observed_base_head=SHA_A,
        observation=observe_queue(
            queued_actions=0,
            rate_remaining=5000,
            now=NOW,
        ),
    )
    assert "policy_matches" in value.failed()


def transaction_fixture(tmp_path):
    transport = configure_collector_transport(ScriptedTransport())
    transport.get_map["queue:Apeloff1/Skeleton"] = 0
    transport.put_map[
        "/repos/Apeloff1/Skeleton/pulls/42/merge"
    ] = {
        "merged": True,
        "sha": SHA_C,
        "message": "merged",
    }
    from skeleton.pr_automation.runner_evidence import EvidenceCollector

    policy = runner_policy()
    collector = EvidenceCollector(transport, policy)
    index = EventIndex(tmp_path / "index.sqlite3")
    transaction = MergeTransaction(
        transport,
        collector,
        index,
        policy,
        clock=lambda: NOW,
    )
    return transport, index, transaction


def test_merge_transaction_applies_exact_head(tmp_path):
    transport, index, transaction = transaction_fixture(tmp_path)
    result = transaction.apply(work_item())
    assert result.state is MutationState.APPLIED
    assert result.merge_sha == SHA_C
    assert transport.put_calls[-1] == (
        "/repos/Apeloff1/Skeleton/pulls/42/merge",
        {"sha": SHA_B, "merge_method": "squash"},
    )


def test_merge_transaction_aborts_when_base_moves(tmp_path):
    transport, index, transaction = transaction_fixture(tmp_path)
    transport.get_map[
        "/repos/Apeloff1/Skeleton/branches/main"
    ] = branch_payload(sha=SHA_C)
    result = transaction.apply(work_item())
    assert result.state is MutationState.ABORTED
    assert "base_head_matches" in result.preconditions.failed()
    assert transport.put_calls == []


def test_merge_transaction_aborts_when_base_unprotected(tmp_path):
    transport, index, transaction = transaction_fixture(tmp_path)
    transport.get_map[
        "/repos/Apeloff1/Skeleton/branches/main"
    ] = branch_payload(sha=SHA_A, protected=False)
    result = transaction.apply(work_item())
    assert result.state is MutationState.ABORTED
    assert "protected_base" in result.preconditions.failed()


def test_merge_transaction_rejected_response(tmp_path):
    transport, index, transaction = transaction_fixture(tmp_path)
    transport.put_map[
        "/repos/Apeloff1/Skeleton/pulls/42/merge"
    ] = {
        "merged": False,
        "message": "branch changed",
    }
    result = transaction.apply(work_item())
    assert result.state is MutationState.REJECTED
    assert "branch changed" in result.message


def test_merge_transaction_duplicate_claim(tmp_path):
    transport, index, transaction = transaction_fixture(tmp_path)
    item = work_item()
    first = transaction.apply(item)
    assert first.state is MutationState.APPLIED
    second = transaction.apply(item)
    assert second.state is MutationState.DUPLICATE


def test_append_receipt_event(tmp_path):
    transport, index, transaction = transaction_fixture(tmp_path)
    item = work_item()
    result = transaction.apply(item)
    assert append_receipt_event(
        index,
        item,
        result,
        delivery_id="12345:42:mutation",
    )
    events = list(index.iter_events("Apeloff1/Skeleton", 42))
    assert events[-1]["event_type"] == "runner_v2:mutation:applied"


@pytest.mark.parametrize(
    "state,expected",
    [
        (MutationState.APPLIED, False),
        (MutationState.DUPLICATE, False),
        (MutationState.ABORTED, True),
        (MutationState.REJECTED, True),
        (MutationState.FAILED, True),
    ],
)
def test_mutation_retriable_semantics(state, expected):
    item = work_item()
    intent = MutationIntent.from_work_item(item, runner_policy())
    from skeleton.pr_automation.runner_contracts import MutationReceipt

    result = MutationReceipt(
        intent=intent,
        state=state,
        observed_head_sha=SHA_B,
        observed_base_sha=SHA_A,
        merge_sha=SHA_C if state is MutationState.APPLIED else None,
        message=state.value,
        preconditions=all_true_preconditions(),
        started_at=NOW.isoformat(),
        finished_at=NOW.isoformat(),
    )
    assert mutation_retriable(result) is expected


def test_transaction_diagnostics_lists_failed_preconditions():
    item = work_item()
    intent = MutationIntent.from_work_item(item, runner_policy())
    from skeleton.pr_automation.runner_contracts import MutationReceipt

    pre = replace(all_true_preconditions(), base_head_matches=False)
    result = MutationReceipt(
        intent=intent,
        state=MutationState.ABORTED,
        observed_head_sha=SHA_B,
        observed_base_sha=SHA_A,
        merge_sha=None,
        message="aborted",
        preconditions=pre,
        started_at=NOW.isoformat(),
        finished_at=NOW.isoformat(),
    )
    assert transaction_diagnostics(result)["failed_preconditions"] == (
        "base_head_matches",
    )


def test_result_counts():
    report = make_report(
        simple_result(number=1, state=WorkState.READY),
        simple_result(number=2, state=WorkState.HELD, decision=Decision.HOLD),
    )
    assert result_counts(report.results) == {"ready": 1, "held": 1}


def test_markdown_summary_contains_target_table():
    report = make_report(simple_result())
    text = markdown_summary(report)
    assert "# PR automation runner v2" in text
    assert "| #42 | ready | ready |" in text


def test_compact_report_contains_fingerprint():
    report = make_report(simple_result())
    compact = compact_report(report)
    assert len(compact["fingerprint"]) == 64
    assert compact["targets"] == 1


def test_report_invariants_clean():
    report = make_report(simple_result())
    assert report_invariants(report) == ()
    assert_report_invariants(report)


def test_report_invariants_detect_mutation_without_authority():
    report = make_report(simple_result())
    from skeleton.pr_automation.runner_contracts import MutationReceipt

    item = work_item()
    intent = MutationIntent.from_work_item(item, runner_policy())
    receipt = MutationReceipt(
        intent=intent,
        state=MutationState.APPLIED,
        observed_head_sha=SHA_B,
        observed_base_sha=SHA_A,
        merge_sha=SHA_C,
        message="merged",
        preconditions=all_true_preconditions(),
        started_at=NOW.isoformat(),
        finished_at=NOW.isoformat(),
    )
    result = simple_result(
        state=WorkState.MERGED,
        decision=Decision.MERGE,
        mutations=(receipt,),
    )
    bad = replace(
        make_report(result),
        admission=replace(admission(), mutation_authorized=False),
    )
    assert "mutation_without_authority" in report_invariants(bad)


def test_report_exit_code_policy_hold_is_zero():
    report = make_report(
        simple_result(state=WorkState.HELD, decision=Decision.HOLD)
    )
    assert report_exit_code(report) == 0


def test_report_exit_code_runtime_failure_is_one():
    report = make_report(
        simple_result(
            state=WorkState.FAILED,
            decision=Decision.HOLD,
            error="boom",
        )
    )
    assert report_exit_code(report) == 1


def test_write_report_json(tmp_path):
    report = make_report(simple_result())
    path = write_report_json(tmp_path / "report.json", report)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["identity"]["repository"] == "Apeloff1/Skeleton"


def test_append_step_summary(tmp_path):
    summary = tmp_path / "summary.md"
    assert append_step_summary(
        "hello",
        {"GITHUB_STEP_SUMMARY": str(summary)},
    )
    assert summary.read_text(encoding="utf-8") == "hello\n"


def test_checkpoint_round_trip(tmp_path):
    report = make_report(simple_result())
    checkpoint = checkpoint_from_report(report)
    path = save_checkpoint(tmp_path / "checkpoint.json", checkpoint)
    loaded = load_checkpoint(path)
    assert loaded == checkpoint
    assert checkpoint_compatible(
        loaded,
        repository=report.identity.repository,
        delivery_id=report.identity.delivery_id,
        policy_fingerprint=report.policy_fingerprint,
    )


def test_csv_normalizes_and_deduplicates():
    assert csv(" A, b,a ", casefold=True) == ("a", "b")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("true", True),
        ("YES", True),
        ("1", True),
        ("false", False),
        ("off", False),
        ("0", False),
    ],
)
def test_env_bool(raw, expected):
    assert env_bool({"X": raw}, "X", not expected) is expected


def test_env_bool_invalid():
    with pytest.raises(ValueError):
        env_bool({"X": "maybe"}, "X", True)


def test_env_int_bounds():
    assert env_int(
        {"X": "5"},
        "X",
        1,
        minimum=1,
        maximum=10,
    ) == 5
    with pytest.raises(ValueError):
        env_int(
            {"X": "11"},
            "X",
            1,
            minimum=1,
            maximum=10,
        )


def test_core_policy_from_env():
    policy = core_policy_from_env(
        {
            "PR_AUTOMATION_ALLOWED_BASES": "main,release",
            "PR_AUTOMATION_REQUIRED_APPROVALS": "2",
            "PR_AUTOMATION_MERGE_WHEN_READY": "true",
        }
    )
    assert policy.allowed_bases == ("main", "release")
    assert policy.required_approvals == 2
    assert policy.merge_when_ready


def test_limits_from_env():
    value = limits_from_env(
        {
            "PR_RUNNER_MAX_TARGETS": "5",
            "PR_AUTOMATION_MAX_MUTATIONS": "2",
            "PR_AUTOMATION_MAX_QUEUED_ACTIONS_RUNS": "20",
        }
    )
    assert value.max_targets == 5
    assert value.max_mutations == 2
    assert value.queue_pressure_threshold == 20


def test_runner_policy_apply_requires_checks():
    with pytest.raises(ValueError, match="requires checks"):
        runner_policy_from_env(
            {
                "PR_AUTOMATION_MODE": "apply",
                "PR_AUTOMATION_MERGE_WHEN_READY": "true",
                "PR_AUTOMATION_REQUIRE_CHECKS": "true",
                "PR_AUTOMATION_REQUIRED_CHECKS": "",
            }
        )


def test_static_runner_contract_is_clean():
    assert check_runner_contract() == ()


def test_every_runner_module_exists():
    for name in MODULES:
        assert (PACKAGE / name).is_file()


def test_each_runner_module_static_contract_is_clean():
    for name in MODULES:
        assert _module_findings(PACKAGE / name) == []


def test_workflow_static_contract_is_clean():
    assert _workflow_findings(
        WORKFLOW.read_text(encoding="utf-8")
    ) == []


def test_cross_file_runner_contract_is_clean():
    assert _cross_file_findings() == []


def test_legacy_runner_contract_is_clean():
    source = (PACKAGE / "runner.py").read_text(encoding="utf-8")
    assert _legacy_findings(source) == []


def test_runner_contract_root_is_repository_root():
    assert (ROOT / ".github" / "workflows").is_dir()
    assert (ROOT / "skeleton" / "pr_automation").is_dir()
