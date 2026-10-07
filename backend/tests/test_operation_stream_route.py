from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from core.operation_stream_transport import OperationStreamTransport
from core.routes_registry import KNOWN_ROUTES_WITH_PREFIX
from routes import operation_stream as route
from skeleton.contracts.operation import OperationEnvelope, OperationState
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


def _operation(
    tenant_id: str = "tenant-a",
    *,
    idempotency_key: str = "idem-route",
) -> OperationEnvelope:
    return OperationEnvelope(
        operation_id=str(uuid4()),
        tenant_id=tenant_id,
        actor_id="actor-a",
        capability="chat",
        created_at=BASE_TIME,
        deadline=BASE_TIME + timedelta(minutes=10),
        idempotency_key=idempotency_key,
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


@pytest.mark.asyncio
async def test_sse_terminal_backlog_drains_across_bounded_batches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, operations, events = _runtime(tmp_path)
    operation = _operation()
    current = operations.create(operation, now=BASE_TIME)
    for index, state in enumerate(
        (
            OperationState.VALIDATED,
            OperationState.AUTHORIZED,
            OperationState.ADMITTED,
            OperationState.RUNNING,
            OperationState.COMPLETED,
        ),
        start=1,
    ):
        current = operations.transition(
            operation.operation_id,
            state,
            expected_version=current.version,
            now=BASE_TIME + timedelta(seconds=index),
        )

    monkeypatch.setattr(route, "_transport", lambda: transport)
    monkeypatch.setattr(route, "_SSE_BATCH_LIMIT", 2)
    monkeypatch.setattr(route, "_POLL_SECONDS", 0.0)

    response = await route.operation_events(
        _Request(),
        operation.operation_id,
        consumer_id="slow-route-client",
        after_sequence=0,
        user={"tenant_id": "tenant-a", "role": "viewer"},
    )

    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(
            chunk.decode("utf-8")
            if isinstance(chunk, bytes)
            else chunk
        )

    payload = "".join(chunks)
    expected_types = (
        "operation.created",
        "operation.validated",
        "operation.authorized",
        "operation.admitted",
        "operation.running",
        "operation.completed",
    )
    offsets = [payload.index("event: " + item) for item in expected_types]
    assert offsets == sorted(offsets)
    assert payload.count("id: ") == 6
    assert payload.count("event: operation.completed") == 1
    assert "event: stream.resync_required" not in payload
    assert "idle-timeout" not in payload

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


@pytest.mark.asyncio
async def test_resync_route_returns_authoritative_compaction_floor(
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

    payload = await route.operation_event_resync(
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



def test_api_reconnect_can_switch_workers_without_cursor_loss(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    operation_path = tmp_path / "shared-operations.sqlite"
    event_path = tmp_path / "shared-events.sqlite"
    operations_a = SQLiteOperationStore(operation_path); operations_b = SQLiteOperationStore(operation_path)
    events_a = SQLiteOperationEventStore(event_path); events_b = SQLiteOperationEventStore(event_path)
    transport_a = OperationStreamTransport(operations_a, events_a, worker_id="worker-a")
    transport_b = OperationStreamTransport(operations_b, events_b, worker_id="worker-b")
    operation = _operation()
    current = operations_a.create(operation, now=BASE_TIME)
    current = operations_a.transition(operation.operation_id, OperationState.VALIDATED, expected_version=current.version, now=BASE_TIME + timedelta(seconds=1))
    try:
        monkeypatch.setattr(route, "_transport", lambda: transport_a)
        first = route.operation_event_replay(operation.operation_id, consumer_id="browser-session-a", after_sequence=0, limit=1, user={"tenant_id": "tenant-a", "role": "viewer"})
        assert [event["sequence"] for event in first["events"]] == [1]
        ack = route.acknowledge_operation_events(operation.operation_id, route.OperationAckRequest(consumer_id="browser-session-a", sequence=1), user={"tenant_id": "tenant-a", "role": "viewer"})
        assert ack["consumer"]["acknowledged_through"] == 1
        current = operations_b.transition(operation.operation_id, OperationState.AUTHORIZED, expected_version=current.version, now=BASE_TIME + timedelta(seconds=2))
        monkeypatch.setattr(route, "_transport", lambda: transport_b)
        resumed = route.operation_event_replay(operation.operation_id, consumer_id="browser-session-a", after_sequence=1, limit=64, user={"tenant_id": "tenant-a", "role": "viewer"})
        assert [event["sequence"] for event in resumed["events"]] == [2, 3]
        assert [event["type"] for event in resumed["events"]] == ["operation.validated", "operation.authorized"]
        assert resumed["stream_latest_sequence"] == 3
    finally:
        operations_a.close(); operations_b.close(); events_a.close(); events_b.close()


def test_slow_browser_replay_on_one_operation_does_not_block_another(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    operation_path = tmp_path / "shared-operations.sqlite"
    event_path = tmp_path / "shared-events.sqlite"
    operations_a = SQLiteOperationStore(operation_path); operations_b = SQLiteOperationStore(operation_path)
    events_a = SQLiteOperationEventStore(event_path); events_b = SQLiteOperationEventStore(event_path)
    transport_a = OperationStreamTransport(operations_a, events_a, worker_id="worker-a")
    transport_b = OperationStreamTransport(operations_b, events_b, worker_id="worker-b")
    slow = _operation()
    fast = _operation(idempotency_key="idem-route-fast")
    slow_current = operations_a.create(slow, now=BASE_TIME)
    for index, state in enumerate((OperationState.VALIDATED, OperationState.AUTHORIZED, OperationState.ADMITTED), start=1):
        slow_current = operations_a.transition(slow.operation_id, state, expected_version=slow_current.version, now=BASE_TIME + timedelta(seconds=index))
    operations_b.create(fast, now=BASE_TIME)
    transport_b.cancel(fast.operation_id, tenant_id="tenant-a")
    try:
        monkeypatch.setattr(route, "_transport", lambda: transport_a)
        first_page = route.operation_event_replay(slow.operation_id, consumer_id="slow-browser", after_sequence=0, limit=1, user={"tenant_id": "tenant-a", "role": "viewer"})
        assert [event["sequence"] for event in first_page["events"]] == [1]
        monkeypatch.setattr(route, "_transport", lambda: transport_b)
        unrelated = route.operation_event_replay(fast.operation_id, consumer_id="fast-browser", after_sequence=0, limit=64, user={"tenant_id": "tenant-a", "role": "viewer"})
        assert unrelated["terminal"] is True
        assert [event["type"] for event in unrelated["events"]] == ["operation.created", "operation.cancelled"]
        resumed_slow = route.operation_event_replay(slow.operation_id, consumer_id="slow-browser", after_sequence=1, limit=64, user={"tenant_id": "tenant-a", "role": "viewer"})
        assert [event["sequence"] for event in resumed_slow["events"]] == [2, 3, 4]
    finally:
        operations_a.close(); operations_b.close(); events_a.close(); events_b.close()
