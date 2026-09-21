from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from skeleton.contracts.operation import (
    OperationContractError,
    OperationEnvelope,
    OperationState,
    OperationTransitionError,
)


def _operation() -> OperationEnvelope:
    now = datetime.now(timezone.utc)
    return OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id="tenant-a",
        actor_id="actor-a",
        capability="chat",
        created_at=now,
        deadline=now + timedelta(minutes=5),
        idempotency_key="idem-1",
        trace_id="trace-1",
    )


def test_operation_contract_has_stable_idempotency_identity() -> None:
    first = _operation()
    second = OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id=first.tenant_id,
        actor_id=first.actor_id,
        capability=first.capability,
        created_at=first.created_at,
        deadline=first.deadline,
        idempotency_key=first.idempotency_key,
        trace_id="different-trace",
    )

    assert first.identity_digest == second.identity_digest
    assert first.operation_id != second.operation_id


def test_operation_lifecycle_allows_declared_path() -> None:
    op = _operation()
    for state in (
        OperationState.VALIDATED,
        OperationState.AUTHORIZED,
        OperationState.ADMITTED,
        OperationState.QUEUED,
        OperationState.RUNNING,
        OperationState.COMPLETED,
    ):
        op = op.transition(state)

    assert op.terminal is True
    assert op.state is OperationState.COMPLETED


def test_operation_lifecycle_rejects_skip_and_post_terminal_transition() -> None:
    op = _operation()
    with pytest.raises(OperationTransitionError):
        op.transition(OperationState.RUNNING)

    completed = (
        op.transition(OperationState.VALIDATED)
        .transition(OperationState.AUTHORIZED)
        .transition(OperationState.ADMITTED)
        .transition(OperationState.RUNNING)
        .transition(OperationState.COMPLETED)
    )
    with pytest.raises(OperationTransitionError):
        completed.transition(OperationState.RUNNING)


def test_operation_requires_aware_ordered_deadline() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(OperationContractError, match="later"):
        OperationEnvelope(
            operation_id=str(uuid4()),
            tenant_id="tenant",
            actor_id="actor",
            capability="chat",
            created_at=now,
            deadline=now,
            idempotency_key="idem",
            trace_id="trace",
        )


def test_operation_expiry_uses_shared_deadline() -> None:
    op = _operation()

    assert op.expired(now=op.created_at) is False
    assert op.expired(now=op.deadline) is True
