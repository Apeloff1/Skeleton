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
        consumer_id="route-client",
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


def test_json_replay_returns_resume_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    operations.create(operation, now=BASE_TIME)
    monkeypatch.setattr(route, "_transport", lambda: transport)

    payload = route.operation_event_replay(
        operation.operation_id,
        consumer_id="route-client",
        after_sequence=0,
        limit=250,
        user={"tenant_id": "tenant-a", "role": "viewer"},
    )

    assert payload["ok"] is True
    assert payload["after_sequence"] == 0
    assert payload["latest_sequence"] == 1
    assert payload["terminal"] is False
    assert payload["events"][0]["type"] == "operation.created"

    operations.close()
    events.close()


def test_json_replay_maps_compaction_gap_to_resync_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    current = operations.transition(
        operation.operation_id,
        "validated",
        expected_version=current.version,
        now=BASE_TIME + timedelta(seconds=1),
    )
    transport.dispatch_pending(operation.operation_id, tenant_id="tenant-a")
    events.compact_through(operation.operation_id, 1)
    monkeypatch.setattr(route, "_transport", lambda: transport)

    with pytest.raises(Exception) as caught:
        route.operation_event_replay(
            operation.operation_id,
            consumer_id="route-client",
            after_sequence=0,
            limit=250,
            user={"tenant_id": "tenant-a", "role": "viewer"},
        )

    assert getattr(caught.value, "status_code", None) == 409
    detail = getattr(caught.value, "detail", {})
    assert detail == {"error": "replay_gap", "resync_required": True}

    operations.close()
    events.close()


def test_route_acknowledges_applied_client_cursor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    operations.create(operation, now=BASE_TIME)
    monkeypatch.setattr(route, "_transport", lambda: transport)

    replay = route.operation_event_replay(
        operation.operation_id,
        consumer_id="route-client",
        after_sequence=0,
        limit=250,
        user={"tenant_id": "tenant-a", "role": "viewer"},
    )
    assert replay["latest_sequence"] == 1

    acknowledged = route.acknowledge_operation_events(
        operation.operation_id,
        route.OperationAckRequest(
            consumer_id="route-client",
            sequence=1,
        ),
        user={"tenant_id": "tenant-a", "role": "viewer"},
    )

    assert acknowledged["ok"] is True
    assert acknowledged["consumer"]["acknowledged_through"] == 1
    assert events.safe_compaction_sequence(operation.operation_id) == 1

    operations.close()
    events.close()


def test_route_ack_is_tenant_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation(tenant_id="tenant-a")
    operations.create(operation, now=BASE_TIME)
    transport.replay(
        operation.operation_id,
        tenant_id="tenant-a",
        consumer_id="route-client",
    )
    monkeypatch.setattr(route, "_transport", lambda: transport)

    with pytest.raises(Exception) as caught:
        route.acknowledge_operation_events(
            operation.operation_id,
            route.OperationAckRequest(
                consumer_id="route-client",
                sequence=1,
            ),
            user={"tenant_id": "tenant-b", "role": "viewer"},
        )

    assert getattr(caught.value, "status_code", None) == 404

    operations.close()
    events.close()


def test_resync_route_returns_authoritative_compaction_floor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    current = operations.transition(
        operation.operation_id,
        "validated",
        expected_version=current.version,
        now=BASE_TIME + timedelta(seconds=1),
    )
    transport.dispatch_pending(operation.operation_id, tenant_id="tenant-a")
    events.compact_through(operation.operation_id, 1)
    monkeypatch.setattr(route, "_transport", lambda: transport)

    payload = route.operation_event_resync(
        operation.operation_id,
        consumer_id="route-resync",
        user={"tenant_id": "tenant-a", "role": "viewer"},
    )

    assert payload["ok"] is True
    assert payload["compacted_through"] == 1
    assert payload["resume_after_sequence"] == 1
    assert payload["latest_sequence"] == 2
    assert payload["operation"]["state"] == "validated"
    assert payload["active_consumer_count"] == 1

    operations.close()
    events.close()


def test_ack_route_compacts_only_after_active_consumers_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    current = operations.transition(
        operation.operation_id,
        "validated",
        expected_version=current.version,
        now=BASE_TIME + timedelta(seconds=1),
    )
    monkeypatch.setattr(route, "_transport", lambda: transport)

    for consumer in ("client-a", "client-b"):
        replay = route.operation_event_replay(
            operation.operation_id,
            consumer_id=consumer,
            after_sequence=0,
            limit=250,
            user={"tenant_id": "tenant-a", "role": "viewer"},
        )
        assert replay["latest_sequence"] == 2

    first = route.acknowledge_operation_events(
        operation.operation_id,
        route.OperationAckRequest(consumer_id="client-a", sequence=2),
        user={"tenant_id": "tenant-a", "role": "viewer"},
    )
    assert first["compacted_through"] == 0
    assert first["active_consumer_count"] == 2

    second = route.acknowledge_operation_events(
        operation.operation_id,
        route.OperationAckRequest(consumer_id="client-b", sequence=1),
        user={"tenant_id": "tenant-a", "role": "viewer"},
    )
    assert second["compacted_through"] == 1
    assert second["compacted_events"] == 1

    operations.close()
    events.close()
