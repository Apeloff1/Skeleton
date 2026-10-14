from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from skeleton.skills.tool_contract import (
    ToolAuthorityClass,
    ToolEffect,
    ToolExecutionRequest,
    ToolExecutionStatus,
    ToolIdempotencyMode,
    ToolManifest,
    ToolSideEffectClass,
)
from skeleton.skills.tool_effect_reconciliation import (
    ReconciliableToolReceiptStore,
    ToolEffectReconciliationConflict,
    ToolEffectReconciliationEvidence,
)
from skeleton.skills.tool_runtime import AsyncToolRuntime
from skeleton.skills.tool_saga import (
    AsyncToolSagaRuntime,
    SQLiteToolSagaStore,
    ToolSagaStatus,
    ToolSagaStep,
)


NOW = datetime(2026, 10, 4, 20, 45, tzinfo=timezone.utc)


def _uid(value: int) -> str:
    return str(UUID(int=value))


def _request(
    *,
    request_id: int = 1,
    key: str = "charge:1",
    tool_id: str = "external.charge",
    operation_id: str | None = None,
) -> ToolExecutionRequest:
    return ToolExecutionRequest(
        request_id=_uid(request_id),
        operation_id=operation_id or _uid(100),
        tenant_id="tenant-a",
        tool_id=tool_id,
        idempotency_key=key,
        arguments={"account": "acct-1", "amount": 7},
        requested_at=NOW,
    )


def _evidence(
    decision: str,
    *,
    result_ref: str | None = None,
    compensation_ref: str | None = None,
    marker: str = "one",
) -> ToolEffectReconciliationEvidence:
    return ToolEffectReconciliationEvidence(
        decision=decision,
        observer_id="external-ledger-observer:v1",
        authority_ref="operator-quorum:g015",
        evidence_refs=(
            f"external-ledger:entry:{marker}",
            f"audit:reconciliation:{marker}",
        ),
        observed_at=NOW,
        result_ref=result_ref,
        compensation_ref=compensation_ref,
        note="independent reconciliation after process loss",
    )


def _forward_manifest() -> ToolManifest:
    return ToolManifest(
        tool_id="external.charge",
        version="1.0.0",
        description="external reversible charge",
        input_schema={
            "type": "object",
            "properties": {
                "account": {"type": "string"},
                "amount": {"type": "integer"},
            },
            "required": ["account", "amount"],
            "additionalProperties": False,
        },
        authority_class=ToolAuthorityClass.EXTERNAL_COMMIT,
        side_effect_class=ToolSideEffectClass.EXTERNAL_REVERSIBLE,
        idempotency_mode=ToolIdempotencyMode.COMPENSATABLE,
        effect=ToolEffect.REVERSIBLE,
        compensation_tool_id="external.refund",
    )


def _compensation_manifest() -> ToolManifest:
    return ToolManifest(
        tool_id="external.refund",
        version="1.0.0",
        description="external reversible refund",
        input_schema={
            "type": "object",
            "properties": {
                "account": {"type": "string"},
                "amount": {"type": "integer"},
            },
            "required": ["account", "amount"],
            "additionalProperties": False,
        },
        authority_class=ToolAuthorityClass.EXTERNAL_COMMIT,
        side_effect_class=ToolSideEffectClass.EXTERNAL_REVERSIBLE,
        idempotency_mode=ToolIdempotencyMode.IDEMPOTENCY_KEY,
        effect=ToolEffect.REVERSIBLE,
    )


def test_committed_effect_reconciliation_replays_without_duplicate_handler(
    tmp_path,
) -> None:
    path = tmp_path / "effects.sqlite3"
    request = _request()
    original = ReconciliableToolReceiptStore(path)
    assert original.reserve(request, now=NOW).status == "owner"
    original.close()

    reopened = ReconciliableToolReceiptStore(path)
    receipt = reopened.reconcile_pending(
        request,
        _evidence(
            "effect_committed",
            result_ref="external-ledger:charge:confirmed",
        ),
        now=NOW,
    )

    assert receipt.status is ToolExecutionStatus.SUCCEEDED
    assert receipt.result_ref == "external-ledger:charge:confirmed"
    assert receipt.metered_tool_calls == 0
    assert receipt.governance_decision_ref.startswith("reconciliation:")
    stored = reopened.get(
        tenant_id=request.tenant_id,
        operation_id=request.operation_id,
        idempotency_key=request.idempotency_key,
    )
    assert stored is not None
    assert stored.status == "committed"
    assert stored.receipt == receipt

    again = reopened.reconcile_pending(
        request,
        _evidence(
            "effect_committed",
            result_ref="external-ledger:charge:confirmed",
        ),
        now=NOW,
    )
    assert again == receipt


@pytest.mark.asyncio
async def test_runtime_consumes_reconciled_receipt_without_reexecuting_effect(
    tmp_path,
) -> None:
    path = tmp_path / "runtime.sqlite3"
    request = _request()
    first = ReconciliableToolReceiptStore(path)
    first.reserve(request, now=NOW)
    first.close()

    reopened = ReconciliableToolReceiptStore(path)
    expected = reopened.reconcile_pending(
        request,
        _evidence(
            "effect_committed",
            result_ref="external-ledger:charge:confirmed",
        ),
        now=NOW,
    )
    calls: list[str] = []

    async def handler(_request: ToolExecutionRequest) -> str:
        calls.append("duplicate-effect")
        return "external-ledger:charge:duplicate"

    runtime = AsyncToolRuntime(receipt_store=reopened)
    await runtime.register(_forward_manifest(), handler)
    replay = await runtime.execute(request, now=NOW)

    assert replay == expected
    assert calls == []


@pytest.mark.asyncio
async def test_absent_effect_becomes_terminal_failure_not_retry(
    tmp_path,
) -> None:
    path = tmp_path / "absent.sqlite3"
    request = _request()
    store = ReconciliableToolReceiptStore(path)
    store.reserve(request, now=NOW)
    receipt = store.reconcile_pending(
        request,
        _evidence("effect_absent"),
        now=NOW,
    )
    assert receipt.status is ToolExecutionStatus.FAILED
    assert receipt.error_code == "reconciled_effect_absent"
    assert receipt.result_ref is None
    assert receipt.metered_tool_calls == 0

    calls: list[str] = []

    async def handler(_request: ToolExecutionRequest) -> str:
        calls.append("unsafe-retry")
        return "unexpected"

    runtime = AsyncToolRuntime(receipt_store=store)
    await runtime.register(_forward_manifest(), handler)
    replay = await runtime.execute(request, now=NOW)
    assert replay == receipt
    assert calls == []


def test_conflicting_reconciliation_evidence_fails_closed(tmp_path) -> None:
    path = tmp_path / "conflict.sqlite3"
    request = _request()
    store = ReconciliableToolReceiptStore(path)
    store.reserve(request, now=NOW)
    store.reconcile_pending(
        request,
        _evidence(
            "effect_committed",
            result_ref="external-ledger:charge:confirmed",
            marker="first",
        ),
        now=NOW,
    )

    with pytest.raises(
        ToolEffectReconciliationConflict,
        match="different evidence",
    ):
        store.reconcile_pending(
            request,
            _evidence(
                "effect_committed",
                result_ref="external-ledger:charge:other",
                marker="second",
            ),
            now=NOW,
        )


def test_reconciliation_is_bound_to_exact_request_identity(tmp_path) -> None:
    path = tmp_path / "identity.sqlite3"
    request = _request()
    store = ReconciliableToolReceiptStore(path)
    store.reserve(request, now=NOW)

    changed = ToolExecutionRequest(
        request_id=_uid(999),
        operation_id=request.operation_id,
        tenant_id=request.tenant_id,
        tool_id=request.tool_id,
        idempotency_key=request.idempotency_key,
        arguments=dict(request.arguments),
        requested_at=NOW,
    )
    with pytest.raises(Exception, match="does not match pending reservation"):
        store.reconcile_pending(
            changed,
            _evidence(
                "effect_committed",
                result_ref="external-ledger:charge:confirmed",
            ),
            now=NOW,
        )


def test_compensated_effect_persists_evidence_and_compensation_ref(
    tmp_path,
) -> None:
    path = tmp_path / "compensated.sqlite3"
    request = _request()
    store = ReconciliableToolReceiptStore(path)
    store.reserve(request, now=NOW)
    evidence = _evidence(
        "effect_compensated",
        compensation_ref="external-ledger:refund:confirmed",
    )
    receipt = store.reconcile_pending(request, evidence, now=NOW)

    assert receipt.status is ToolExecutionStatus.FAILED
    assert receipt.error_code == "reconciled_effect_compensated"
    assert receipt.compensation_ref == "external-ledger:refund:confirmed"
    assert store.reconciliation_evidence(
        tenant_id=request.tenant_id,
        operation_id=request.operation_id,
        idempotency_key=request.idempotency_key,
    ) == evidence
    binding = store.reconciliation_receipt(
        tenant_id=request.tenant_id,
        operation_id=request.operation_id,
        idempotency_key=request.idempotency_key,
    )
    assert binding is not None
    assert binding.evidence_digest == evidence.digest
    assert binding.terminal_receipt_id == receipt.receipt_id


@pytest.mark.asyncio
async def test_saga_does_not_double_compensate_reconciled_compensated_effect(
    tmp_path,
) -> None:
    operation_id = _uid(1000)
    forward = _request(
        request_id=10,
        key="charge:saga",
        operation_id=operation_id,
    )
    compensation = ToolExecutionRequest(
        request_id=_uid(11),
        operation_id=operation_id,
        tenant_id="tenant-a",
        tool_id="external.refund",
        idempotency_key="refund:saga",
        arguments={"account": "acct-1", "amount": 7},
        requested_at=NOW,
    )
    step = ToolSagaStep(
        forward=forward,
        compensation=compensation,
    )

    receipt_store = ReconciliableToolReceiptStore(
        tmp_path / "saga-tool.sqlite3"
    )
    receipt_store.reserve(forward, now=NOW)
    receipt_store.reconcile_pending(
        forward,
        _evidence(
            "effect_compensated",
            compensation_ref="external-ledger:refund:already-done",
        ),
        now=NOW,
    )

    forward_calls: list[str] = []
    compensation_calls: list[str] = []

    async def forward_handler(_request: ToolExecutionRequest) -> str:
        forward_calls.append("forward")
        return "unexpected-forward"

    async def compensation_handler(_request: ToolExecutionRequest) -> str:
        compensation_calls.append("compensate")
        return "unexpected-compensation"

    tools = AsyncToolRuntime(receipt_store=receipt_store)
    await tools.register(_forward_manifest(), forward_handler)
    await tools.register(_compensation_manifest(), compensation_handler)
    saga = AsyncToolSagaRuntime(
        tools,
        SQLiteToolSagaStore(tmp_path / "saga.sqlite3"),
    )

    receipt = await saga.execute(
        _uid(2000),
        (step,),
        owner_token=_uid(3000),
        now=NOW,
    )

    assert receipt.status is ToolSagaStatus.FAILED
    assert receipt.error_code == "reconciled_effect_compensated"
    assert forward_calls == []
    assert compensation_calls == []
