from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from skeleton.jeeves.agent.audit_assurance import FrontierExecutionReplayVerifier
from skeleton.jeeves.agent.durable_audit import (
    DurableAuditError,
    SQLiteExecutionAuditStore,
)
from skeleton.jeeves.agent.execution_audit import (
    AuditEventKind,
    AuditSeverity,
    ReplayIssueKind,
)
from skeleton.jeeves.agent.frontier_runtime import ScopedGeneralizingRuntimeEpistemicGuard
from skeleton.jeeves.agent.policy import PolicyDecision
from skeleton.jeeves.agent.runtime_guard import RuntimeGuardRequest, RuntimeGuardSignals
from skeleton.jeeves.agent.tools import (
    ArgumentRule,
    ToolExecutionContext,
    ToolExecutor,
    ToolGrant,
    ToolRegistry,
    ToolSpec,
)
from skeleton.jeeves.agent.types import (
    Budget,
    Decision,
    RiskTier,
    ToolCall,
    Usage,
    stable_fingerprint,
)


def test_durable_audit_survives_store_reconstruction(tmp_path) -> None:
    path = tmp_path / "jeeves.sqlite3"
    first = SQLiteExecutionAuditStore(path)
    ledger = first.get_or_create("run-durable-audit")
    one = ledger.append(
        AuditEventKind.INTENT_BOUND,
        {
            "intent_id": "intent-a",
            "intent_fingerprint": "a" * 64,
            "call_id": "call-a",
            "tool_name": "read_record",
        },
        operation_id="operation-a",
        severity=AuditSeverity.SECURITY,
    )
    two = ledger.append(
        AuditEventKind.DECISION_MADE,
        {
            "decision_id": "decision-a",
            "decision_fingerprint": "b" * 64,
            "disposition": "act",
        },
        operation_id="operation-a",
        severity=AuditSeverity.SECURITY,
    )

    second = SQLiteExecutionAuditStore(path)
    restored = second.get("run-durable-audit")

    assert restored is not None
    assert restored.event_count == 2
    assert restored.head_hash == two.event_hash
    assert restored.entries() == (one, two)
    assert restored.entries()[1].previous_hash == one.event_hash


def test_sqlite_transaction_serializes_concurrent_sequence_assignment(tmp_path) -> None:
    store = SQLiteExecutionAuditStore(tmp_path / "audit.sqlite3")
    run_id = "run-concurrent-audit"

    def append(index: int) -> int:
        entry = store.get_or_create(run_id).append(
            AuditEventKind.EXECUTION_FAILED,
            {"reason": f"synthetic-failure-{index}"},
            operation_id=f"operation-{index}",
        )
        return entry.sequence

    with ThreadPoolExecutor(max_workers=8) as pool:
        sequences = list(pool.map(append, range(32)))

    assert sorted(sequences) == list(range(1, 33))
    ledger = store.get_or_create(run_id)
    assert ledger.event_count == 32
    generic = store.verify(run_id)
    assert generic.valid


def test_direct_database_payload_tamper_is_detected_by_replay(tmp_path) -> None:
    path = tmp_path / "audit.sqlite3"
    store = SQLiteExecutionAuditStore(path)
    ledger = store.get_or_create("run-tamper")
    ledger.append(
        AuditEventKind.EXECUTION_FAILED,
        {"reason": "original"},
        operation_id="operation-tamper",
    )

    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "UPDATE jeeves_execution_audit SET payload_json=? WHERE run_id=? AND sequence=1",
            (json.dumps({"reason": "forged"}), "run-tamper"),
        )
        conn.commit()
    finally:
        conn.close()

    report = store.verify("run-tamper")
    assert not report.valid
    assert any(
        issue.kind is ReplayIssueKind.EVENT_HASH_MISMATCH
        for issue in report.issues
    )


def test_store_rejects_wall_clock_regression_before_commit(tmp_path) -> None:
    path = tmp_path / "audit.sqlite3"
    store = SQLiteExecutionAuditStore(path)
    ledger = store.get_or_create("run-clock")
    ledger.append(
        AuditEventKind.EXECUTION_FAILED,
        {"reason": "first"},
        operation_id="operation-first",
        at=100.0,
    )

    with pytest.raises(DurableAuditError, match="moved backwards"):
        ledger.append(
            AuditEventKind.EXECUTION_FAILED,
            {"reason": "second"},
            operation_id="operation-second",
            at=99.0,
        )

    assert ledger.event_count == 1


def test_frontier_guard_tool_observation_is_durable_before_execute_returns(tmp_path) -> None:
    path = tmp_path / "frontier.sqlite3"
    audit_store = SQLiteExecutionAuditStore(path)
    registry = ToolRegistry()
    spec = ToolSpec(
        name="read_restart_record",
        description="Read one restart test record.",
        risk=RiskTier.READ_ONLY,
        arguments=(ArgumentRule("record_id", "string"),),
    )
    registry.register(spec, lambda arguments, context: {"ok": True, "value": 11})
    executor = ToolExecutor(registry)
    guard = ScopedGeneralizingRuntimeEpistemicGuard(
        executor,
        audit_store=audit_store,
    )
    call = ToolCall(
        call_id="call-restart",
        name=spec.name,
        arguments={"record_id": "fixture"},
    )
    request = RuntimeGuardRequest(
        run_id="run-restart-observation",
        goal_id="goal-restart",
        step_id="step-restart",
        attempt=1,
        plan_version=1,
        call=call,
        execution_context=ToolExecutionContext(
            run_id="run-restart-observation",
            user_id="user-restart",
            trace_id="trace-restart",
        ),
        tool_spec=spec,
        grants=(
            ToolGrant(
                tool_name=spec.name,
                allowed_risks=(RiskTier.READ_ONLY,),
                max_calls=2,
                argument_fingerprint=stable_fingerprint(call.arguments),
            ),
        ),
        host_policy_decision=PolicyDecision(
            Decision.ALLOW,
            "host allowed",
            "durable-audit-policy",
            risk=RiskTier.READ_ONLY,
        ),
        confirmed_actions=(),
        usage=Usage(),
        budget=Budget(),
        signals=RuntimeGuardSignals(
            progress=0.2,
            uncertainty=0.5,
            budget_pressure=0.1,
            failure_pressure=0.0,
        ),
        metadata={"tenant_id": "tenant-a", "workspace_id": "workspace-a"},
    )

    execution = guard.execute(request)
    assert execution.observation.ok

    # Simulate a fresh process: only reopen the SQLite database. No in-memory
    # guard/pending state is reused.
    reopened = SQLiteExecutionAuditStore(path)
    ledger = reopened.get("run-restart-observation")
    assert ledger is not None
    entries = ledger.entries()
    assert entries[-1].kind is AuditEventKind.TOOL_OBSERVED
    assert entries[-1].payload["observation_fingerprint"] == execution.observation_fingerprint

    report = FrontierExecutionReplayVerifier().verify(
        entries,
        expected_run_id="run-restart-observation",
        require_finalized_operations=False,
    )
    assert report.valid
    assert len(report.operations) == 1
    assert report.operations[0].observation_fingerprint == execution.observation_fingerprint
    assert report.operations[0].finalized is False