from __future__ import annotations

from skeleton.jeeves.agent.audit_assurance import FrontierExecutionReplayVerifier
from skeleton.jeeves.agent.execution_audit import (
    AuditEventKind,
    AuditSeverity,
    ExecutionAuditLedger,
    ReplayIssueKind,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64


def _payload(version: int = 5) -> dict[str, object]:
    payload: dict[str, object] = {
        "frontier_binding_version": version,
        "checkpoint_sequence": 1,
        "checkpoint_fingerprint": SHA_A,
        "audit_head_before": "0" * 64,
        "audit_events_before": 0,
        "audit_checkpoint_before": SHA_B,
        "runtime_guard_policy": SHA_C,
        "transition_model_fingerprint": SHA_D,
        "transition_model_lineage_count": 0,
        "transition_model_lineage_hash": SHA_E,
        "world_model_fingerprint": SHA_F,
    }
    if version == 5:
        payload.update(
            {
                "semantic_scoping_enabled": True,
                "semantic_learning_scope_fingerprint": SHA_A,
                "semantic_plane_fingerprint": SHA_B,
                "semantic_runtime_state_fingerprint": SHA_C,
                "semantic_topology_learning_fingerprint": SHA_D,
            }
        )
    return payload


def _verify(payload: dict[str, object]):
    ledger = ExecutionAuditLedger("run-checkpoint-binding", clock=lambda: 1.0)
    ledger.append(
        AuditEventKind.CHECKPOINT_BOUND,
        payload,
        severity=AuditSeverity.SECURITY,
    )
    return FrontierExecutionReplayVerifier().verify(
        ledger.entries(),
        expected_run_id=ledger.run_id,
    )


def test_frontier_checkpoint_binding_v5_is_accepted() -> None:
    report = _verify(_payload())
    assert report.valid is True
    assert report.issues == ()


def test_frontier_checkpoint_binding_v2_remains_accepted() -> None:
    report = _verify(_payload(version=2))
    assert report.valid is True
    assert report.issues == ()


def test_frontier_checkpoint_binding_v5_requires_semantic_identity() -> None:
    payload = _payload()
    payload.pop("semantic_plane_fingerprint")
    report = _verify(payload)

    assert report.valid is False
    assert any(
        issue.kind is ReplayIssueKind.REQUIRED_FIELD_MISSING
        and "semantic_plane_fingerprint" in issue.message
        for issue in report.issues
    )


def test_frontier_checkpoint_binding_v5_requires_boolean_scoping_flag() -> None:
    payload = _payload()
    payload["semantic_scoping_enabled"] = "true"
    report = _verify(payload)

    assert report.valid is False
    assert any(
        issue.kind is ReplayIssueKind.CHECKPOINT_MISMATCH
        and "semantic_scoping_enabled must be boolean" in issue.message
        for issue in report.issues
    )


def test_frontier_checkpoint_binding_unknown_version_fails_closed() -> None:
    report = _verify(_payload(version=4))

    assert report.valid is False
    assert any(
        issue.kind is ReplayIssueKind.CHECKPOINT_MISMATCH
        and issue.message == "unsupported frontier checkpoint binding version"
        and issue.actual == 4
        for issue in report.issues
    )
