from dataclasses import replace

import pytest

from core.cockpit_execution_projection import project_execution_evidence
from core.execution_evidence import derive_lifecycle


def evidence():
    operation_id = "op-demo-1"
    detail = '{"operation_id":"op-demo-1"}'
    return derive_lifecycle(
        operation_id,
        pending_operations=[
            {
                "operation_id": operation_id,
                "executor_bound": True,
                "payload": {"secret": "must-not-project"},
            }
        ],
        receipts=[],
        audit_entries=[
            {"seq": 1, "kind": "operation_admitted", "detail": detail},
        ],
    )


def test_projection_exposes_only_bounded_operator_evidence():
    source = evidence()
    projected = project_execution_evidence(source)
    payload = projected.as_dict()

    assert payload == {
        "operationId": "op-demo-1",
        "state": "pending_bound",
        "confidence": "high",
        "pending": True,
        "executorBound": True,
        "receiptPresent": False,
        "anomalyCount": 0,
        "anomalies": [],
        "evidenceSha256": source.evidence_sha256,
        "writable": False,
    }
    rendered = repr(payload)
    assert "secret" not in rendered
    assert "payload" not in rendered
    assert "audit_sequences" not in rendered


def test_projection_rejects_tampered_evidence_digest_by_default():
    source = evidence()
    tampered = replace(source, state="confirmed")
    with pytest.raises(ValueError, match="verification failed"):
        project_execution_evidence(tampered)


def test_projection_can_be_used_for_already_verified_evidence_without_rehashing():
    source = evidence()
    tampered = replace(source, evidence_sha256="0" * 64)
    projected = project_execution_evidence(tampered, require_verified_digest=False)
    assert projected.evidence_sha256 == "0" * 64
    assert projected.writable is False


def test_projection_bounds_identifiers_and_anomaly_publication():
    source = evidence()
    bad_operation = replace(source, operation_id="has spaces")
    with pytest.raises(ValueError, match="operation_id"):
        project_execution_evidence(bad_operation, require_verified_digest=False)

    many_anomalies = replace(
        source,
        anomalies=tuple(f"anomaly_{index}" for index in range(20)),
    )
    projected = project_execution_evidence(
        many_anomalies,
        require_verified_digest=False,
    )
    assert projected.anomaly_count == 20
    assert len(projected.anomalies) == 16
    assert projected.anomalies[0] == "anomaly_0"
    assert projected.anomalies[-1] == "anomaly_15"
