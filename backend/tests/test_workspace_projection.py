from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from core.operation_projection import (
    apply_projection_events,
    start_projection,
    verify_projection_authority,
)
from core.operation_stream_transport import OperationStreamTransport
from core.workspace_projection import (
    BlockerProjection,
    BlockerSeverity,
    CostProjection,
    ProgressProjection,
    TerminalResultProjection,
    WorkspaceProjectionError,
    build_workspace_projection,
    verify_workspace_projection,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.operation import OperationEnvelope, OperationState
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.operation_store import SQLiteOperationStore


BASE_TIME = datetime(2026, 9, 28, 13, 0, tzinfo=timezone.utc)


def _evidence(
    source: str,
    digest: str,
    category: str,
) -> EvidenceRef:
    return EvidenceRef(
        source=source,
        digest=digest,
        category=category,
    )


def _operation(
    *,
    tenant_id: str = "tenant-a",
    idempotency_key: str = "workspace-projection",
) -> OperationEnvelope:
    return OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id=tenant_id,
        actor_id="actor-a",
        capability="chat",
        created_at=BASE_TIME,
        deadline=BASE_TIME + timedelta(minutes=20),
        idempotency_key=idempotency_key,
        trace_id="trace-workspace",
    )


def _runtime(tmp_path: Path):
    operations = SQLiteOperationStore(tmp_path / "operations.sqlite")
    events = SQLiteOperationEventStore(tmp_path / "events.sqlite")
    transport = OperationStreamTransport(
        operations,
        events,
        worker_id="workspace-projection-test",
    )
    return transport, operations, events


def _advance(
    operations: SQLiteOperationStore,
    current,
    *states: OperationState,
):
    for index, state in enumerate(states, start=1):
        current = operations.transition(
            current.envelope.operation_id,
            state,
            expected_version=current.version,
            now=BASE_TIME + timedelta(seconds=index),
        )
    return current


def _verified_projection(transport, authority):
    batch = transport.replay(
        authority.envelope.operation_id,
        tenant_id=authority.envelope.tenant_id,
        after_sequence=0,
        limit=64,
    )
    projection = apply_projection_events(
        start_projection(authority),
        batch.events,
    )
    decision = verify_projection_authority(
        projection,
        authority,
    )
    assert decision.accepted is True
    return projection, decision


def test_workspace_projection_is_view_over_verified_operation_truth(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    current = _advance(
        operations,
        current,
        OperationState.VALIDATED,
        OperationState.AUTHORIZED,
    )
    try:
        projection, authority = _verified_projection(
            transport,
            current,
        )
        progress = ProgressProjection(
            completed_units=3,
            total_units=10,
            label="Analyzing repository",
            evidence=_evidence(
                "ci://progress/3",
                "1" * 64,
                "operation_progress",
            ),
        )
        blocker = BlockerProjection(
            blocker_id="waiting-ci",
            summary="A required validation is still running.",
            severity=BlockerSeverity.WARNING,
            evidence=_evidence(
                "ci://blocker/waiting-ci",
                "2" * 64,
                "operation_blocker",
            ),
        )
        cost = CostProjection(
            spent_units=1.25,
            remaining_units=3.75,
            unit="cost-unit",
            evidence=_evidence(
                "ci://cost/current",
                "3" * 64,
                "operation_cost",
            ),
        )
        workspace = build_workspace_projection(
            operation_projection=projection,
            authority=authority,
            progress=progress,
            blockers=(blocker,),
            cost=cost,
            evidence=(
                _evidence(
                    "ci://evidence/quality",
                    "4" * 64,
                    "quality",
                ),
            ),
        )
        decision = verify_workspace_projection(
            workspace,
            projection,
            authority,
        )

        assert workspace.canonical_state is OperationState.AUTHORIZED
        assert workspace.operation_version == current.version
        assert workspace.cursor_sequence == current.version
        assert workspace.terminal is False
        assert workspace.progress is progress
        assert workspace.progress.fraction == pytest.approx(0.3)
        assert workspace.blockers == (blocker,)
        assert workspace.cost is cost
        assert decision.accepted is True
        evidence = decision.accepted_evidence_ref()
        assert evidence.category == "workspace_projection_authority"
        assert evidence.digest == decision.decision_digest
    finally:
        operations.close()
        events.close()


def test_cached_workspace_cannot_invent_canonical_state(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    current = _advance(
        operations,
        current,
        OperationState.VALIDATED,
        OperationState.AUTHORIZED,
    )
    try:
        projection, authority = _verified_projection(
            transport,
            current,
        )
        workspace = build_workspace_projection(
            operation_projection=projection,
            authority=authority,
        )
        forged = replace(
            workspace,
            canonical_state=OperationState.RUNNING,
        )

        decision = verify_workspace_projection(
            forged,
            projection,
            authority,
        )

        assert decision.accepted is False
        assert "canonical-state-mismatch" in decision.reasons
        with pytest.raises(
            WorkspaceProjectionError,
            match="cannot become promotion",
        ):
            decision.accepted_evidence_ref()
    finally:
        operations.close()
        events.close()


def test_workspace_tenant_substitution_is_detected(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    try:
        projection, authority = _verified_projection(
            transport,
            current,
        )
        workspace = build_workspace_projection(
            operation_projection=projection,
            authority=authority,
        )
        forged = replace(workspace, tenant_id="tenant-b")

        decision = verify_workspace_projection(
            forged,
            projection,
            authority,
        )

        assert decision.accepted is False
        assert "tenant-id-mismatch" in decision.reasons
    finally:
        operations.close()
        events.close()


def test_stale_workspace_is_rejected_after_operation_advances(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    current = _advance(
        operations,
        current,
        OperationState.VALIDATED,
    )
    try:
        projection, authority = _verified_projection(
            transport,
            current,
        )
        workspace = build_workspace_projection(
            operation_projection=projection,
            authority=authority,
        )

        current = operations.transition(
            operation.operation_id,
            OperationState.AUTHORIZED,
            expected_version=current.version,
            now=BASE_TIME + timedelta(seconds=5),
        )
        fresh_projection, fresh_authority = _verified_projection(
            transport,
            current,
        )
        decision = verify_workspace_projection(
            workspace,
            fresh_projection,
            fresh_authority,
        )

        assert decision.accepted is False
        assert "operation-version-mismatch" in decision.reasons
        assert "cursor-sequence-mismatch" in decision.reasons
        assert "operation-projection-digest-mismatch" in decision.reasons
        assert "projection-authority-digest-mismatch" in decision.reasons
    finally:
        operations.close()
        events.close()


def test_rejected_operation_projection_authority_cannot_build_workspace(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    try:
        projection, authority = _verified_projection(
            transport,
            current,
        )
        rejected = replace(
            authority,
            accepted=False,
            reasons=("authority-rejected",),
        )

        with pytest.raises(
            WorkspaceProjectionError,
            match="authority must be accepted",
        ):
            build_workspace_projection(
                operation_projection=projection,
                authority=rejected,
            )
    finally:
        operations.close()
        events.close()


def test_authority_projection_digest_substitution_is_rejected(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    try:
        projection, authority = _verified_projection(
            transport,
            current,
        )
        forged = replace(
            authority,
            projection_digest="0" * 64,
        )

        with pytest.raises(
            WorkspaceProjectionError,
            match="operation projection digest mismatch",
        ):
            build_workspace_projection(
                operation_projection=projection,
                authority=forged,
            )
    finally:
        operations.close()
        events.close()


def test_terminal_workspace_requires_provenance_bound_result(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    current = _advance(
        operations,
        current,
        OperationState.VALIDATED,
        OperationState.AUTHORIZED,
        OperationState.ADMITTED,
        OperationState.RUNNING,
        OperationState.COMPLETED,
    )
    try:
        projection, authority = _verified_projection(
            transport,
            current,
        )

        with pytest.raises(
            WorkspaceProjectionError,
            match="terminal projection requires terminal_result",
        ):
            build_workspace_projection(
                operation_projection=projection,
                authority=authority,
            )

        terminal = TerminalResultProjection(
            summary="Operation completed with verified result.",
            result=_evidence(
                "ci://result/final",
                "5" * 64,
                "operation_result",
            ),
        )
        workspace = build_workspace_projection(
            operation_projection=projection,
            authority=authority,
            progress=ProgressProjection(
                completed_units=10,
                total_units=10,
                label="Complete",
                evidence=_evidence(
                    "ci://progress/complete",
                    "6" * 64,
                    "operation_progress",
                ),
            ),
            terminal_result=terminal,
        )
        decision = verify_workspace_projection(
            workspace,
            projection,
            authority,
        )

        assert workspace.terminal is True
        assert workspace.canonical_state is OperationState.COMPLETED
        assert workspace.terminal_result is terminal
        assert decision.accepted is True
    finally:
        operations.close()
        events.close()


def test_nonterminal_workspace_cannot_claim_terminal_result(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    try:
        projection, authority = _verified_projection(
            transport,
            current,
        )
        terminal = TerminalResultProjection(
            summary="Forged local result.",
            result=_evidence(
                "local://forged-result",
                "7" * 64,
                "operation_result",
            ),
        )

        with pytest.raises(
            WorkspaceProjectionError,
            match="non-terminal projection cannot include terminal_result",
        ):
            build_workspace_projection(
                operation_projection=projection,
                authority=authority,
                terminal_result=terminal,
            )
    finally:
        operations.close()
        events.close()


def test_progress_and_cost_bounds_fail_closed() -> None:
    with pytest.raises(
        WorkspaceProjectionError,
        match="completed_units cannot exceed total_units",
    ):
        ProgressProjection(
            completed_units=11,
            total_units=10,
            label="Impossible progress",
            evidence=_evidence(
                "ci://progress/bad",
                "8" * 64,
                "operation_progress",
            ),
        )

    with pytest.raises(
        WorkspaceProjectionError,
        match="finite and non-negative",
    ):
        CostProjection(
            spent_units=-1.0,
            remaining_units=1.0,
            unit="cost-unit",
            evidence=_evidence(
                "ci://cost/bad",
                "9" * 64,
                "operation_cost",
            ),
        )


def test_duplicate_blocker_identity_is_rejected(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    try:
        projection, authority = _verified_projection(
            transport,
            current,
        )
        blocker = BlockerProjection(
            blocker_id="same-blocker",
            summary="Same blocker identity.",
            severity=BlockerSeverity.BLOCKING,
            evidence=_evidence(
                "ci://blocker/same",
                "a" * 64,
                "operation_blocker",
            ),
        )
        with pytest.raises(
            WorkspaceProjectionError,
            match="blocker IDs must be unique",
        ):
            build_workspace_projection(
                operation_projection=projection,
                authority=authority,
                blockers=(blocker, blocker),
            )
    finally:
        operations.close()
        events.close()


def test_workspace_evidence_is_deduplicated_deterministically(
    tmp_path: Path,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    try:
        projection, authority = _verified_projection(
            transport,
            current,
        )
        first = _evidence(
            "ci://evidence/a",
            "b" * 64,
            "quality",
        )
        second = _evidence(
            "ci://evidence/b",
            "c" * 64,
            "quality",
        )
        one = build_workspace_projection(
            operation_projection=projection,
            authority=authority,
            evidence=(second, first, first),
        )
        two = build_workspace_projection(
            operation_projection=projection,
            authority=authority,
            evidence=(first, second),
        )

        assert one.evidence == two.evidence
        assert one.projection_digest == two.projection_digest
    finally:
        operations.close()
        events.close()
