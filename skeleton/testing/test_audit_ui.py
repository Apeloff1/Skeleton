from __future__ import annotations

from skeleton.ai.runtime.deferred.deployment_operations_assurance import project_audit_event
from skeleton.ai.runtime.deferred.operations_experience import AuditEvent

A="a"*64
B="b"*64

def test_audit_projection_binds_sequence_provenance_and_trace()->None:
    record=project_audit_event(
        AuditEvent(1,"event-1","actor","approve","release-1",A),
        provenance_digest=B,trace_id="trace-1",
    )
    assert record.sequence==1
    assert record.payload_digest==A
    assert record.provenance_digest==B
    assert record.trace_id=="trace-1"
