from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from core.operation_stream_transport import OperationStreamTransport
from core.routes_registry import KNOWN_ROUTES_WITH_PREFIX
from routes import operation_stream as route
from skeleton.contracts.operation import OperationEnvelope
from skeleton.frontier.operation_stream_store import SQLiteOperationEventStore
from skeleton.persistence.operation_store import SQLiteOperationStore


BASE_TIME = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


class _Request:
    def __init__(self, last_event_id: str | None = None) -> None:
        self.headers = {}
        if last_event_id is not None:
            self.headers["last-event-id"] = last_event_id

    async def is_disconnected(self) -> bool:
        return False


def _operation(tenant_id: str = "tenant-a") -> OperationEnvelope:
    return OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id=tenant_id,
        actor_id="actor-a",
        capability="chat",
        created_at=BASE_TIME,
        deadline=BASE_TIME + timedelta(minutes=10),
        idempotency_key="idem-route",
        trace_id="trace-route",
    )


def _runtime(tmp_path: Path):
    operations = SQLiteOperationStore(tmp_path / "operations.sqlite")
    events = SQLiteOperationEventStore(tmp_path / "events.sqlite")
    transport = OperationStreamTransport(operations, events)
    return transport, operations, events


def test_operation_router_is_declared_under_api_prefix() -> None:
    assert ("routes.operation_stream", "router", "/api") in KNOWN_ROUTES_WITH_PREFIX


def test_last_event_id_header_is_used_when_query_cursor_is_absent() -> None:
    assert route._last_event_sequence(_Request("17"), None) == 17
    assert route._last_event_sequence(_Request("17"), 3) == 3


def test_invalid_last_event_id_fails_closed() -> None:
    with pytest.raises(Exception) as caught:
        route._last_event_sequence(_Request("1.5"), None)

    assert getattr(caught.value, "status_code", None) == 400


def test_principal_tenant_prefers_explicit_tenant_id() -> None:
    assert route._principal_tenant(
        {"tenant_id": "tenant-explicit", "email": "person@example.com"}
    ) == "tenant-explicit"
    assert route._principal_tenant({"email": "person@example.com"}) == "person@example.com"


def test_status_and_cancel_are_tenant_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    operations.create(operation, now=BASE_TIME)
    monkeypatch.setattr(route, "_transport", lambda: transport)

    status = route.operation_status(
        operation.operation_id,
        user={"tenant_id": "tenant-a", "role": "viewer"},
    )
    cancelled = route.cancel_operation(
        operation.operation_id,
        user={"tenant_id": "tenant-a", "role": "viewer"},
    )

    assert status["operation"]["state"] == "created"
    assert cancelled["changed"] is True
    assert cancelled["operation"]["state"] == "cancelled"

    with pytest.raises(Exception) as caught:
        route.operation_status(
            operation.operation_id,
            user={"tenant_id": "tenant-b", "role": "viewer"},
        )
    assert getattr(caught.value, "status_code", None) == 404

    operations.close()
    events.close()


@pytest.mark.asyncio
async def test_terminal_sse_replay_emits_canonical_events_and_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    operations.create(operation, now=BASE_TIME)
    transport.cancel(operation.operation_id, tenant_id="tenant-a")
    monkeypatch.setattr(route, "_transport", lambda: transport)

    response = await route.operation_events(
        _Request(),
        operation.operation_id,
        after_sequence=0,
        user={"tenant_id": "tenant-a", "role": "viewer"},
    )

    chunks: list[str] = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8"))
        else:
            chunks.append(chunk)

    payload = "".join(chunks)
    assert "event: operation.created" in payload
    assert "event: operation.cancelled" in payload
    assert "event: stream.resync_required" not in payload

    operations.close()
    events.close()
