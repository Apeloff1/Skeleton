"""End-to-end orchestration regressions for runner v2."""

from __future__ import annotations

from dataclasses import replace

from skeleton.pr_automation.core import Decision, Mode
from skeleton.pr_automation.index import EventIndex
from skeleton.pr_automation.runner_contracts import (
    AdmissionDecision,
    AdmissionState,
    PriorityBand,
    RunTrigger,
    WorkState,
)
from skeleton.pr_automation.runner_engine import (
    report_has_merge,
    report_result,
    run_engine,
    successful_target_numbers,
)
from skeleton.testing.runner_v2_test_support import (
    NOW,
    SHA_B,
    SHA_C,
    ScriptedTransport,
    admission,
    branch_payload,
    configure_collector_transport,
    identity,
    pr_payload,
    runner_policy,
    threads_payload,
)


def explicit_transport() -> ScriptedTransport:
    transport = configure_collector_transport(ScriptedTransport())
    # Engine apply performs one evaluation snapshot and one independent
    # mutation-boundary refresh, each with its own review-thread query.
    transport.graphql_queue.append(threads_payload(unresolved=0))
    transport.get_map["queue:Apeloff1/Skeleton"] = 0
    transport.put_map[
        "/repos/Apeloff1/Skeleton/pulls/42/merge"
    ] = {
        "merged": True,
        "sha": SHA_C,
        "message": "merged",
    }
    return transport


def test_engine_observe_mode_never_mutates(tmp_path):
    transport = explicit_transport()
    policy = replace(runner_policy(), mode=Mode.OBSERVE)
    report = run_engine(
        transport=transport,
        index=EventIndex(tmp_path / "index.sqlite3"),
        policy=policy,
        identity=identity(),
        admission=replace(admission(), mutation_authorized=False),
        clock=lambda: NOW,
    )
    assert report.mutations_attempted == 0
    assert transport.put_calls == []
    assert report.results[0].state is WorkState.READY


def test_engine_apply_mode_merges_ready_pr(tmp_path):
    transport = explicit_transport()
    report = run_engine(
        transport=transport,
        index=EventIndex(tmp_path / "index.sqlite3"),
        policy=runner_policy(),
        identity=identity(),
        admission=admission(),
        clock=lambda: NOW,
    )
    assert report.mutations_attempted == 1
    assert report.mutations_applied == 1
    assert report_has_merge(report, 42)
    assert report_result(report, 42).state is WorkState.MERGED


def test_engine_persists_evaluation_and_mutation_events(tmp_path):
    transport = explicit_transport()
    index = EventIndex(tmp_path / "index.sqlite3")
    report = run_engine(
        transport=transport,
        index=index,
        policy=runner_policy(),
        identity=identity(),
        admission=admission(),
        clock=lambda: NOW,
    )
    events = list(index.iter_events("Apeloff1/Skeleton", 42))
    kinds = [event["event_type"] for event in events]
    assert "runner_v2:evaluation" in kinds
    assert "runner_v2:mutation:applied" in kinds


def test_engine_status_is_published_before_merge(tmp_path):
    transport = explicit_transport()
    run_engine(
        transport=transport,
        index=EventIndex(tmp_path / "index.sqlite3"),
        policy=runner_policy(),
        identity=identity(),
        admission=admission(),
        clock=lambda: NOW,
    )
    assert transport.post_calls
    path, body = transport.post_calls[0]
    assert path == f"/repos/Apeloff1/Skeleton/statuses/{SHA_B}"
    assert body["context"] == "PR Automation Gate"
    assert body["state"] == "success"


def test_engine_holds_base_head_move_without_mutation(tmp_path):
    transport = configure_collector_transport(
        ScriptedTransport(),
        base=branch_payload(sha=SHA_C),
    )
    transport.get_map["queue:Apeloff1/Skeleton"] = 0
    report = run_engine(
        transport=transport,
        index=EventIndex(tmp_path / "index.sqlite3"),
        policy=runner_policy(),
        identity=identity(),
        admission=admission(),
        clock=lambda: NOW,
    )
    result = report_result(report, 42)
    assert result.state is WorkState.HELD
    assert result.decision is Decision.HOLD
    assert "base_head_mismatch" in result.reasons
    assert transport.put_calls == []


def test_engine_holds_fork_without_mutation(tmp_path):
    transport = configure_collector_transport(
        ScriptedTransport(),
        pr=pr_payload(head_repo="fork/Skeleton"),
    )
    transport.get_map["queue:Apeloff1/Skeleton"] = 0
    report = run_engine(
        transport=transport,
        index=EventIndex(tmp_path / "index.sqlite3"),
        policy=runner_policy(),
        identity=identity(),
        admission=admission(),
        clock=lambda: NOW,
    )
    result = report_result(report, 42)
    assert result.state is WorkState.HELD
    assert transport.put_calls == []


def test_engine_queue_pressure_defers_mutation(tmp_path):
    transport = explicit_transport()
    transport.get_map["queue:Apeloff1/Skeleton"] = 999
    report = run_engine(
        transport=transport,
        index=EventIndex(tmp_path / "index.sqlite3"),
        policy=runner_policy(),
        identity=identity(),
        admission=admission(),
        clock=lambda: NOW,
    )
    result = report_result(report, 42)
    assert result.state is WorkState.DEFERRED
    assert "queue_pressure" in result.reasons
    assert transport.put_calls == []
    assert transport.post_calls[-1][1]["state"] == "pending"
    assert "queue_pressure" in transport.post_calls[-1][1]["description"]


def test_engine_mutation_budget_zero_defers_ready_pr(tmp_path):
    transport = explicit_transport()
    policy = replace(
        runner_policy(),
        limits=replace(runner_policy().limits, max_mutations=0),
    )
    report = run_engine(
        transport=transport,
        index=EventIndex(tmp_path / "index.sqlite3"),
        policy=policy,
        identity=identity(),
        admission=admission(),
        clock=lambda: NOW,
    )
    result = report_result(report, 42)
    assert result.state is WorkState.DEFERRED
    assert "mutation_budget_exhausted" in result.reasons


def test_engine_per_target_request_budget_defers_before_mutation(tmp_path):
    transport = explicit_transport()
    policy = replace(
        runner_policy(),
        limits=replace(
            runner_policy().limits,
            per_target_request_budget=1,
        ),
    )
    report = run_engine(
        transport=transport,
        index=EventIndex(tmp_path / "index.sqlite3"),
        policy=policy,
        identity=identity(),
        admission=admission(),
        clock=lambda: NOW,
    )
    result = report_result(report, 42)
    assert result.state is WorkState.DEFERRED
    assert any(
        reason.startswith("per_target_request_budget_exceeded:")
        for reason in result.reasons
    )
    assert transport.put_calls == []


def test_engine_drop_does_not_read_repository(tmp_path):
    transport = ScriptedTransport()
    dropped = AdmissionDecision(
        state=AdmissionState.DROP,
        reasons=("firewall",),
        mutation_authorized=False,
        priority=PriorityBand.COMPLETION,
        identity_fingerprint=identity().fingerprint(),
    )
    report = run_engine(
        transport=transport,
        index=EventIndex(tmp_path / "index.sqlite3"),
        policy=runner_policy(),
        identity=identity(
            trigger=RunTrigger.RECOVERY,
            explicit_pr=None,
        ),
        admission=dropped,
        clock=lambda: NOW,
    )
    assert report.targets.targets == ()
    assert report.transport.requests == 0
    assert report.results == ()


def test_engine_ambiguous_merge_dispatch_is_hard_failure(tmp_path):
    transport = explicit_transport()
    transport.put_map[
        "/repos/Apeloff1/Skeleton/pulls/42/merge"
    ] = TimeoutError("connection lost after request dispatch")

    report = run_engine(
        transport=transport,
        index=EventIndex(tmp_path / "index.sqlite3"),
        policy=runner_policy(),
        identity=identity(),
        admission=admission(),
        clock=lambda: NOW,
    )

    result = report_result(report, 42)
    assert result.state is WorkState.FAILED
    assert result.error is not None
    assert "outcome uncertain" in result.error
    assert report.failures == 1
    assert len(transport.put_calls) == 1
    assert transport.post_calls[-1][1]["state"] == "error"


def test_engine_runtime_collection_failure_isolated_to_target(tmp_path):
    transport = ScriptedTransport()
    transport.get_map[
        "/repos/Apeloff1/Skeleton/pulls/42"
    ] = RuntimeError("boom")
    report = run_engine(
        transport=transport,
        index=EventIndex(tmp_path / "index.sqlite3"),
        policy=runner_policy(),
        identity=identity(),
        admission=replace(admission(), mutation_authorized=False),
        clock=lambda: NOW,
    )
    result = report_result(report, 42)
    assert result.state is WorkState.FAILED
    assert "RuntimeError: boom" in result.error
    assert report.failures == 1


def test_engine_sweep_deferred_results_for_target_cap(tmp_path):
    transport = ScriptedTransport()
    transport.list_map[
        "/repos/Apeloff1/Skeleton/pulls?state=open&sort=updated&direction=asc"
    ] = (
        [
            pr_payload(number=1, head_ref="feature/1"),
            pr_payload(number=2, head_ref="feature/2"),
        ],
        True,
    )
    policy = replace(
        runner_policy(),
        mode=Mode.OBSERVE,
        limits=replace(runner_policy().limits, max_targets=1),
    )
    ident = identity(
        trigger=RunTrigger.MANUAL_SWEEP,
        explicit_pr=None,
    )

    # Only the first selected target is collected because the resolver itself is
    # bounded to max_targets. This regression locks that discovery contract.
    configure_collector_transport(
        transport,
        number=1,
        pr=pr_payload(number=1, head_ref="feature/1"),
    )
    report = run_engine(
        transport=transport,
        index=EventIndex(tmp_path / "index.sqlite3"),
        policy=policy,
        identity=ident,
        admission=replace(admission(), mutation_authorized=False),
        clock=lambda: NOW,
    )
    assert len(report.targets.targets) == 1
    assert report.targets.targets[0].number == 1


def test_successful_target_numbers_excludes_failures(tmp_path):
    transport = explicit_transport()
    report = run_engine(
        transport=transport,
        index=EventIndex(tmp_path / "index.sqlite3"),
        policy=replace(runner_policy(), mode=Mode.OBSERVE),
        identity=identity(),
        admission=replace(admission(), mutation_authorized=False),
        clock=lambda: NOW,
    )
    assert successful_target_numbers(report) == (42,)
