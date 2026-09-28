from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from core.operation_projection import (
    apply_projection_events,
    start_projection,
)
from core.product_shell_projection import (
    ProductProjectionError,
    project_workspace_product_state,
)
from skeleton.contracts.operation import OperationEnvelope, OperationState
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.operation_stream import StreamEvent
from skeleton.persistence.operation_store import StoredOperation


BASE_TIME = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def _envelope(
    state: OperationState = OperationState.CREATED,
    *,
    tenant_id: str = "tenant-a",
) -> OperationEnvelope:
    return OperationEnvelope(
        operation_id="00000000-0000-4000-8000-000000000001",
        tenant_id=tenant_id,
        actor_id="actor-a",
        capability="chat",
        created_at=BASE_TIME,
        deadline=BASE_TIME + timedelta(minutes=10),
        idempotency_key="prod-03-test",
        trace_id="trace-prod-03",
        state=state,
    )


def _stored(
    state: OperationState,
    version: int,
    *,
    tenant_id: str = "tenant-a",
) -> StoredOperation:
    return StoredOperation(
        envelope=_envelope(state, tenant_id=tenant_id),
        version=version,
        updated_at=BASE_TIME + timedelta(seconds=version),
    )


def _event(
    sequence: int,
    state: OperationState,
    *,
    payload: dict | None = None,
) -> StreamEvent:
    body = {
        "state": state.value,
        "version": sequence,
        "trace_id": "trace-prod-03",
        **(payload or {}),
    }
    return StreamEvent(
        operation_id="00000000-0000-4000-8000-000000000001",
        event_id=f"10000000-0000-4000-8000-{sequence:012d}",
        sequence=sequence,
        type=f"operation.{state.value}",
        timestamp=BASE_TIME + timedelta(seconds=sequence),
        payload=body,
    )


def _running_chain(*, supplemental: dict | None = None):
    authority = _stored(OperationState.RUNNING, 5)
    events = (
        _event(1, OperationState.CREATED),
        _event(2, OperationState.VALIDATED),
        _event(3, OperationState.AUTHORIZED),
        _event(4, OperationState.ADMITTED),
        _event(5, OperationState.RUNNING, payload=supplemental),
    )
    projection = apply_projection_events(
        start_projection(authority),
        events,
    )
    return authority, projection, events


def test_projection_is_read_only_and_bound_to_durable_authority() -> None:
    authority, projection, events = _running_chain(
        supplemental={
            "progress": 0.72,
            "progress_label": "Generating verified answer",
            "blockers": [
                {
                    "blocker_id": "tool-latency",
                    "summary": "Tool response is delayed.",
                    "evidence_digest": "a" * 64,
                }
            ],
            "cost": {
                "currency": "usd",
                "spent": 0.25,
                "budget": 1.0,
            },
            "evidence": [
                {
                    "source": "receipt://tool-1",
                    "digest": "b" * 64,
                    "category": "tool_receipt",
                }
            ],
        }
    )

    product = project_workspace_product_state(
        authority=authority,
        projection=projection,
        events=events,
    )

    assert product.operation_id == authority.envelope.operation_id
    assert product.tenant_id == "tenant-a"
    assert product.operation_state == "running"
    assert product.operation_version == 5
    assert product.cursor_sequence == 5
    assert product.progress == pytest.approx(0.72)
    assert product.progress_label == "Generating verified answer"
    assert product.writable is False
    assert product.cost is not None
    assert product.cost.currency == "USD"
    assert product.cost.spent == pytest.approx(0.25)
    assert product.cost.budget == pytest.approx(1.0)
    assert [item.blocker_id for item in product.blockers] == ["tool-latency"]
    assert product.evidence[0].digest == "b" * 64
    assert product.terminal_result is None
    assert product.authority_digest == stable_content_digest(authority.as_dict())
    assert len(product.projection_digest) == 64
    assert product.evidence_ref().category == "workspace_product_projection"


def test_waiting_state_derives_blocker_without_inventing_external_reason() -> None:
    authority = _stored(OperationState.WAITING_FOR_USER, 6)
    events = (
        _event(1, OperationState.CREATED),
        _event(2, OperationState.VALIDATED),
        _event(3, OperationState.AUTHORIZED),
        _event(4, OperationState.ADMITTED),
        _event(5, OperationState.RUNNING),
        _event(6, OperationState.WAITING_FOR_USER),
    )
    projection = apply_projection_events(start_projection(authority), events)

    product = project_workspace_product_state(
        authority=authority,
        projection=projection,
        events=events,
    )

    assert product.progress == pytest.approx(0.65)
    assert [item.blocker_id for item in product.blockers] == [
        "state:waiting-for-user"
    ]


def test_explicit_blocker_can_be_resolved_by_later_accepted_event() -> None:
    authority = _stored(OperationState.RUNNING, 7)
    events = (
        _event(1, OperationState.CREATED),
        _event(2, OperationState.VALIDATED),
        _event(3, OperationState.AUTHORIZED),
        _event(4, OperationState.ADMITTED),
        _event(
            5,
            OperationState.RUNNING,
            payload={
                "blockers": [
                    {
                        "blocker_id": "dependency",
                        "summary": "Dependency unavailable.",
                    }
                ]
            },
        ),
        _event(6, OperationState.RETRYING),
        _event(
            7,
            OperationState.RUNNING,
            payload={
                "blockers": [
                    {
                        "blocker_id": "dependency",
                        "active": False,
                        "summary": "ignored",
                    }
                ]
            },
        ),
    )
    projection = apply_projection_events(start_projection(authority), events)

    product = project_workspace_product_state(
        authority=authority,
        projection=projection,
        events=events,
    )
    assert all(item.blocker_id != "dependency" for item in product.blockers)

def test_cost_cannot_regress_or_change_currency() -> None:
    authority = _stored(OperationState.RUNNING, 5)
    events = (
        _event(
            1,
            OperationState.CREATED,
            payload={"cost": {"currency": "USD", "spent": 0.5, "budget": 1.0}},
        ),
        _event(
            2,
            OperationState.VALIDATED,
            payload={"cost": {"currency": "USD", "spent": 0.4, "budget": 1.0}},
        ),
        _event(3, OperationState.AUTHORIZED),
        _event(4, OperationState.ADMITTED),
        _event(5, OperationState.RUNNING),
    )
    projection = apply_projection_events(start_projection(authority), events)

    with pytest.raises(ProductProjectionError, match="cannot decrease"):
        project_workspace_product_state(
            authority=authority,
            projection=projection,
            events=events,
        )


def test_event_payload_must_match_exact_accepted_receipt() -> None:
    authority, projection, events = _running_chain()
    original = events[-1]
    tampered = StreamEvent(
        operation_id=original.operation_id,
        event_id=original.event_id,
        sequence=original.sequence,
        type=original.type,
        timestamp=original.timestamp,
        payload={
            **dict(original.payload),
            "progress": 0.99,
        },
    )

    with pytest.raises(ProductProjectionError, match="receipt digest mismatch"):
        project_workspace_product_state(
            authority=authority,
            projection=projection,
            events=(*events[:-1], tampered),
        )


def test_event_outside_receipt_window_is_not_trusted() -> None:
    authority, projection, events = _running_chain()
    projection = replace(projection, recent_events=projection.recent_events[-1:])

    with pytest.raises(ProductProjectionError, match="outside exact accepted"):
        project_workspace_product_state(
            authority=authority,
            projection=projection,
            events=events,
        )


def test_stale_or_cross_tenant_projection_cannot_overwrite_authority() -> None:
    authority, projection, events = _running_chain()
    stale = replace(projection, operation_version=4)

    with pytest.raises(ProductProjectionError, match="does not match durable authority"):
        project_workspace_product_state(
            authority=authority,
            projection=stale,
            events=events,
        )

    other_tenant = _stored(OperationState.RUNNING, 5, tenant_id="tenant-b")
    with pytest.raises(ProductProjectionError, match="does not match durable authority"):
        project_workspace_product_state(
            authority=other_tenant,
            projection=projection,
            events=events,
        )


def test_terminal_completed_result_projects_reference_and_content_digest() -> None:
    authority = _stored(OperationState.COMPLETED, 6)
    events = (
        _event(1, OperationState.CREATED),
        _event(2, OperationState.VALIDATED),
        _event(3, OperationState.AUTHORIZED),
        _event(4, OperationState.ADMITTED),
        _event(5, OperationState.RUNNING),
        _event(
            6,
            OperationState.COMPLETED,
            payload={
                "result": {
                    "status": "completed",
                    "final_output": "canonical final answer",
                    "result_ref": "result:final",
                    "message_id": "message:final",
                }
            },
        ),
    )
    projection = apply_projection_events(start_projection(authority), events)

    product = project_workspace_product_state(
        authority=authority,
        projection=projection,
        events=events,
    )

    assert product.progress == 1.0
    assert product.terminal_result is not None
    assert product.terminal_result.status == "completed"
    assert product.terminal_result.result_ref == "result:final"
    assert product.terminal_result.message_id == "message:final"
    assert product.terminal_result.final_output_digest == stable_content_digest(
        "canonical final answer"
    )


def test_terminal_failure_never_projects_final_output_digest() -> None:
    authority = _stored(OperationState.FAILED, 6)
    events = (
        _event(1, OperationState.CREATED),
        _event(2, OperationState.VALIDATED),
        _event(3, OperationState.AUTHORIZED),
        _event(4, OperationState.ADMITTED),
        _event(5, OperationState.RUNNING),
        _event(
            6,
            OperationState.FAILED,
            payload={
                "failure_code": "provider_unavailable",
                "final_output": "must-not-be-treated-as-success",
            },
        ),
    )
    projection = apply_projection_events(start_projection(authority), events)

    product = project_workspace_product_state(
        authority=authority,
        projection=projection,
        events=events,
    )

    assert product.terminal_result is not None
    assert product.terminal_result.status == "failed"
    assert product.terminal_result.failure_code == "provider_unavailable"
    assert product.terminal_result.final_output_digest is None
