from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from skeleton.skills.tool_contract import (
    ToolExecutionRequest,
    ToolExecutionStatus,
    ToolManifest,
)
from skeleton.skills.tool_receipt_store import SQLiteToolReceiptStore
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
