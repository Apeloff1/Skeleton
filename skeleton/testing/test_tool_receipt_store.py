from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from skeleton.skills.tool_contract import (
    ToolExecutionReceipt,
    ToolExecutionRequest,
    ToolExecutionStatus,
    ToolManifest,
)
from skeleton.skills.tool_receipt_store import (
    SQLiteToolReceiptStore,
    ToolReceiptConflict,
    ToolReconciliationOutcome,
)
from skeleton.skills.tool_runtime import AsyncToolRuntime, ToolRuntime


def _now():
    return datetime(2026, 9, 23, 20, 0, tzinfo=timezone.utc)


def _manifest():
    return ToolManifest(
        tool_id="repo.read",
        version="1.0.0",
        description="Read a repository file",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    )


def _request():
    return ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=str(uuid4()),
        tenant_id="tenant-a",
        tool_id="repo.read",
        idempotency_key="stable-restart-key",
        arguments={"path": "README.md"},
        requested_at=_now(),
    )


def test_sync_durable_receipt_replays_after_restart_without_handler(tmp_path) -> None:
    path = tmp_path / "tool-receipts.sqlite3"
    calls = []
    request = _request()

    store = SQLiteToolReceiptStore(path)
    first = ToolRuntime(receipt_store=store)
    first.register(
        _manifest(),
        lambda req: calls.append("first") or "artifact:readme",
    )
    original = first.execute(request, now=_now())
    store.close()

    reopened = SQLiteToolReceiptStore(path)
    second = ToolRuntime(receipt_store=reopened)
    second.register(
        _manifest(),
        lambda req: calls.append("duplicate") or "artifact:duplicate",
    )
    replay = second.execute(request, now=_now())

    assert original.status is ToolExecutionStatus.SUCCEEDED
    assert replay == original
    assert calls == ["first"]


@pytest.mark.asyncio
async def test_async_durable_receipt_replays_after_restart_without_handler(
    tmp_path,
) -> None:
    path = tmp_path / "tool-receipts.sqlite3"
    calls = []
    request = _request()

    async def first_handler(_request):
        calls.append("first")
        return "artifact:readme"

    store = SQLiteToolReceiptStore(path)
    first = AsyncToolRuntime(receipt_store=store)
    await first.register(_manifest(), first_handler)
    original = await first.execute(request, now=_now())
    store.close()

    async def duplicate_handler(_request):
        calls.append("duplicate")
        return "artifact:duplicate"

    reopened = SQLiteToolReceiptStore(path)
    second = AsyncToolRuntime(receipt_store=reopened)
    await second.register(_manifest(), duplicate_handler)
    replay = await second.execute(request, now=_now())

    assert replay == original
    assert calls == ["first"]


@pytest.mark.asyncio
async def test_abandoned_pending_reservation_fails_closed_after_restart(
    tmp_path,
) -> None:
    path = tmp_path / "tool-receipts.sqlite3"
    request = _request()

    first_store = SQLiteToolReceiptStore(path)
    reservation = first_store.reserve(request, now=_now())
    assert reservation.status == "owner"
    first_store.close()

    effects = []

    async def handler(_request):
        effects.append("effect")
        return "artifact:should-not-run"

    reopened = SQLiteToolReceiptStore(path)
    runtime = AsyncToolRuntime(receipt_store=reopened)
    await runtime.register(_manifest(), handler)

    receipt = await runtime.execute(request, now=_now())

    assert receipt.status is ToolExecutionStatus.DENIED
    assert receipt.error_code == "execution_in_doubt"
    assert receipt.metered_tool_calls == 0
    assert effects == []
    assert reopened.pending() == (
        ("tenant-a", request.operation_id, request.idempotency_key),
    )


def test_durable_store_rejects_idempotency_key_reuse_with_different_args(
    tmp_path,
) -> None:
    path = tmp_path / "tool-receipts.sqlite3"
    store = SQLiteToolReceiptStore(path)
    first = _request()
    store.reserve(first, now=_now())

    conflicting = ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=first.operation_id,
        tenant_id=first.tenant_id,
        tool_id=first.tool_id,
        idempotency_key=first.idempotency_key,
        arguments={"path": "OTHER.md"},
        requested_at=_now(),
    )

    with pytest.raises(Exception, match="different tool or arguments"):
        store.reserve(conflicting, now=_now())

def test_durable_receipt_preserves_execution_turn_call_lineage_across_restart(
    tmp_path,
) -> None:
    path = tmp_path / "tool-lineage-receipts.sqlite3"
    execution_id = str(uuid4())
    turn_id = str(uuid4())
    call_id = str(uuid4())
    request = ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=str(uuid4()),
        execution_id=execution_id,
        turn_id=turn_id,
        call_id=call_id,
        tenant_id="tenant-a",
        tool_id="repo.read",
        idempotency_key="lineage-restart-key",
        arguments={"path": "README.md"},
        requested_at=_now(),
    )
    calls = []

    first_store = SQLiteToolReceiptStore(path)
    first_runtime = ToolRuntime(receipt_store=first_store)
    first_runtime.register(
        _manifest(),
        lambda _request: calls.append("first") or "artifact:lineage",
    )
    original = first_runtime.execute(request, now=_now())
    first_store.close()

    assert original.execution_id == execution_id
    assert original.turn_id == turn_id
    assert original.call_id == call_id
    assert original.as_dict()["execution_id"] == execution_id
    assert original.as_dict()["turn_id"] == turn_id
    assert original.as_dict()["call_id"] == call_id

    reopened = SQLiteToolReceiptStore(path)
    second_runtime = ToolRuntime(receipt_store=reopened)
    second_runtime.register(
        _manifest(),
        lambda _request: calls.append("duplicate") or "artifact:duplicate",
    )
    replay = second_runtime.execute(request, now=_now())

    assert replay == original
    assert replay.execution_id == execution_id
    assert replay.turn_id == turn_id
    assert replay.call_id == call_id
    assert calls == ["first"]


def test_durable_store_rejects_lineage_change_for_same_idempotency_identity(
    tmp_path,
) -> None:
    path = tmp_path / "tool-lineage-conflict.sqlite3"
    operation_id = str(uuid4())
    execution_id = str(uuid4())
    turn_id = str(uuid4())
    first = ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        call_id=str(uuid4()),
        tenant_id="tenant-a",
        tool_id="repo.read",
        idempotency_key="lineage-conflict-key",
        arguments={"path": "README.md"},
        requested_at=_now(),
    )
    store = SQLiteToolReceiptStore(path)
    store.reserve(first, now=_now())

    conflicting = ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        call_id=str(uuid4()),
        tenant_id="tenant-a",
        tool_id="repo.read",
        idempotency_key=first.idempotency_key,
        arguments={"path": "README.md"},
        requested_at=_now(),
    )

    with pytest.raises(Exception, match="different tool or arguments"):
        store.reserve(conflicting, now=_now())


def test_existing_receipt_database_migrates_nullable_lineage_columns(tmp_path) -> None:
    import sqlite3

    path = tmp_path / "legacy-tool-receipts.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE tool_execution_receipt (
            namespace TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            operation_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            request_id TEXT NOT NULL,
            tool_id TEXT NOT NULL,
            arguments_digest TEXT NOT NULL,
            state TEXT NOT NULL,
            reserved_at TEXT NOT NULL,
            receipt_json TEXT,
            completed_at TEXT,
            PRIMARY KEY(namespace, tenant_id, operation_id, idempotency_key)
        );
        """
    )
    connection.close()

    store = SQLiteToolReceiptStore(path)
    columns = {
        row[1]
        for row in store._connection.execute(
            "PRAGMA table_info(tool_execution_receipt)"
        ).fetchall()
    }

    assert {
        "execution_id",
        "turn_id",
        "call_id",
        "data_class",
        "transfer_purpose",
    }.issubset(columns)

def test_durable_receipt_preserves_privacy_context_across_restart(
    tmp_path,
) -> None:
    path = tmp_path / "tool-privacy-receipts.sqlite3"
    request = ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=str(uuid4()),
        tenant_id="tenant-a",
        tool_id="repo.read",
        idempotency_key="privacy-restart-key",
        arguments={"path": "README.md"},
        requested_at=_now(),
        data_class="public",
        transfer_purpose="verification",
    )
    calls = []

    first_store = SQLiteToolReceiptStore(path)
    first_runtime = ToolRuntime(receipt_store=first_store)
    first_runtime.register(
        _manifest(),
        lambda _request: calls.append("first") or "artifact:privacy",
    )
    original = first_runtime.execute(request, now=_now())
    first_store.close()

    assert original.data_class == "public"
    assert original.transfer_purpose == "verification"
    assert original.governance_decision_ref.startswith("gov-tool-")

    reopened = SQLiteToolReceiptStore(path)
    second_runtime = ToolRuntime(receipt_store=reopened)
    second_runtime.register(
        _manifest(),
        lambda _request: calls.append("duplicate") or "artifact:duplicate",
    )
    replay = second_runtime.execute(request, now=_now())

    assert replay == original
    assert replay.data_class == "public"
    assert replay.transfer_purpose == "verification"
    assert calls == ["first"]


def test_durable_store_rejects_privacy_context_change_for_same_identity(
    tmp_path,
) -> None:
    path = tmp_path / "tool-privacy-conflict.sqlite3"
    operation_id = str(uuid4())
    first = ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=operation_id,
        tenant_id="tenant-a",
        tool_id="repo.read",
        idempotency_key="privacy-conflict-key",
        arguments={"path": "README.md"},
        requested_at=_now(),
        data_class="internal",
    )
    store = SQLiteToolReceiptStore(path)
    store.reserve(first, now=_now())

    conflicting = ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=operation_id,
        tenant_id="tenant-a",
        tool_id="repo.read",
        idempotency_key=first.idempotency_key,
        arguments={"path": "README.md"},
        requested_at=_now(),
        data_class="public",
    )

    with pytest.raises(Exception, match="privacy context"):
        store.reserve(conflicting, now=_now())


def _receipt_for(request):
    return ToolExecutionReceipt(
        receipt_id=str(uuid4()),
        request_id=request.request_id,
        operation_id=request.operation_id,
        execution_id=request.execution_id,
        turn_id=request.turn_id,
        call_id=request.call_id,
        tenant_id=request.tenant_id,
        tool_id=request.tool_id,
        idempotency_key=request.idempotency_key,
        arguments_digest=request.arguments_digest,
        status=ToolExecutionStatus.SUCCEEDED,
        started_at=_now(),
        finished_at=_now(),
        result_ref="artifact:reconciled",
        data_class=request.data_class,
        transfer_purpose=request.transfer_purpose,
    )


def test_no_effect_reconciliation_releases_only_current_fence(tmp_path) -> None:
    path = tmp_path / "tool-reconciliation.sqlite3"
    request = _request()
    store = SQLiteToolReceiptStore(path)
    assert store.reserve(request, now=_now()).status == "owner"

    resolved = store.resolve_no_effect(
        request,
        evidence_ref="audit:no-effect-1",
        now=_now(),
    )
    assert resolved.outcome is ToolReconciliationOutcome.NO_EFFECT
    assert resolved.reference.startswith("tool-reconciliation:")
    assert store.pending() == ()
    assert store.reconciliation(
        tenant_id=request.tenant_id,
        operation_id=request.operation_id,
        idempotency_key=request.idempotency_key,
    ) == resolved

    # A retry may acquire a fresh fence only after no-effect reconciliation.
    assert store.reserve(request, now=_now()).status == "owner"

    # The old evidence cannot be reused to release this new incident.
    with pytest.raises(ToolReceiptConflict, match="already consumed"):
        store.resolve_no_effect(
            request,
            evidence_ref="audit:no-effect-1",
            now=_now(),
        )
    assert store.pending() == (
        (request.tenant_id, request.operation_id, request.idempotency_key),
    )

    second = store.resolve_no_effect(
        request,
        evidence_ref="audit:no-effect-2",
        now=_now(),
    )
    assert second.reconciliation_id != resolved.reconciliation_id
    assert store.pending() == ()


def test_no_effect_reconciliation_is_idempotent_after_release(tmp_path) -> None:
    path = tmp_path / "tool-reconciliation-idempotent.sqlite3"
    request = _request()
    store = SQLiteToolReceiptStore(path)
    store.reserve(request, now=_now())

    first = store.resolve_no_effect(
        request,
        evidence_ref="audit:no-effect",
        now=_now(),
    )
    second = store.resolve_no_effect(
        request,
        evidence_ref="audit:no-effect",
        now=_now(),
    )
    assert second == first


def test_committed_reconciliation_preserves_canonical_receipt(tmp_path) -> None:
    path = tmp_path / "tool-reconciliation-commit.sqlite3"
    request = _request()
    store = SQLiteToolReceiptStore(path)
    store.reserve(request, now=_now())
    receipt = _receipt_for(request)

    reconciliation = store.resolve_committed(
        request,
        receipt,
        evidence_ref="audit:effect-confirmed",
        now=_now(),
    )
    assert reconciliation.outcome is ToolReconciliationOutcome.COMMITTED
    assert reconciliation.receipt_id == receipt.receipt_id
    durable = store.get(
        tenant_id=request.tenant_id,
        operation_id=request.operation_id,
        idempotency_key=request.idempotency_key,
    )
    assert durable is not None
    assert durable.status == "committed"
    assert durable.receipt == receipt


def test_committed_execution_cannot_be_reconciled_as_no_effect(tmp_path) -> None:
    path = tmp_path / "tool-reconciliation-conflict.sqlite3"
    request = _request()
    store = SQLiteToolReceiptStore(path)
    store.reserve(request, now=_now())
    receipt = _receipt_for(request)
    store.commit(request, receipt, now=_now())

    with pytest.raises(ToolReceiptConflict, match="cannot reconcile as no-effect"):
        store.resolve_no_effect(
            request,
            evidence_ref="audit:false-no-effect",
            now=_now(),
        )
