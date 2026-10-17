"""Realtime client <-> hub integration: connect, publish, drop, reconnect, resume.

In-process transport (exact SSE endpoint semantics) plus a real HTTP round
trip through uvicorn, the x-gf-seal gate and ``GET /api/v1/events``.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest

from skeleton.client.realtime import (
    InProcessTransport,
    RealtimeAuthError,
    RealtimeClient,
    ReconnectBackoff,
    SSETransport,
)
from skeleton.realtime.hub import sealed_principal_authorizer
from skeleton.realtime import RealtimeHub
from skeleton.realtime.envelope import ControlEvent, RealtimeEvent


async def _no_sleep(_delay: float) -> None:
    await asyncio.sleep(0)


def _backoff():
    return ReconnectBackoff(rng=lambda lo, hi: 0.0)


async def _take(agen, n, timeout=5.0):
    out = []
    while len(out) < n:
        out.append(await asyncio.wait_for(agen.__anext__(), timeout))
    return out


def _active_sub(hub):
    with hub._lock:
        return next(iter(hub._subs.values()), None)


async def _wait_for_sub(hub, previous=None, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sub = _active_sub(hub)
        if sub is not None and sub is not previous:
            return sub
        await asyncio.sleep(0.01)
    raise AssertionError("no subscriber connected")


def test_connect_publish_drop_reconnect_resume_in_process():
    async def scenario():
        hub = RealtimeHub(authorizer=sealed_principal_authorizer, id_seed=100, heartbeat_interval_s=0.05)
        client = RealtimeClient(InProcessTransport(hub, principal="ui"), channels=("build",), backoff=_backoff(), sleep=_no_sleep)
        events = client.events()
        pending = asyncio.ensure_future(_take(events, 2))
        first_sub = await _wait_for_sub(hub)
        hub.publish("build", "build.started", {"step": 1}, job_id="job-1", owner="ui")
        hub.publish("build", "build.progress", {"step": 2}, job_id="job-1", owner="ui")
        got = await pending
        assert [e.id for e in got] == ["101", "102"]
        # Server drops the connection; two events land while the client is away.
        hub.unsubscribe(first_sub, reason="test_drop")
        hub.publish("build", "build.progress", {"step": 3}, job_id="job-1", owner="ui")
        hub.publish("build", "build.completed", {"step": 4}, job_id="job-1", owner="ui")
        resumed = await _take(events, 2)
        assert [e.id for e in resumed] == ["103", "104"]
        assert client.last_event_id == "104"
        assert client.stats["reconnects"] == 1
        slo = hub.slo.snapshot()["counters"]
        assert slo["resume_attempts"] == 1 and slo["resume_successes"] == 1
        assert slo["events_resumed"] + slo["events_delivered"] >= 4
        client.close()
        await events.aclose()

    asyncio.run(scenario())


def test_lagged_client_reconnects_and_recovers_every_event():
    async def scenario():
        hub = RealtimeHub(authorizer=sealed_principal_authorizer, id_seed=0, subscriber_queue=2, heartbeat_interval_s=0.05)
        client = RealtimeClient(InProcessTransport(hub, principal="ui"), channels=("build",), backoff=_backoff(), sleep=_no_sleep)
        frames = client.frames()
        first = asyncio.ensure_future(_take(frames, 1))
        await _wait_for_sub(hub)
        for i in range(6):  # burst while the consumer is not reading
            hub.publish("build", "build.log", {"i": i}, owner="ui")
        (lagged,) = await first
        assert isinstance(lagged, ControlEvent) and lagged.type == "stream.lagged"
        rest = await _take(frames, 6)
        assert [f.id for f in rest if isinstance(f, RealtimeEvent)] == [str(i) for i in range(1, 7)]
        assert client.stats["lagged"] == 1 and client.stats["reconnects"] == 1
        client.close()
        await frames.aclose()

    asyncio.run(scenario())


def test_stream_reset_invokes_callback_and_moves_cursor():
    async def scenario():
        hub = RealtimeHub(authorizer=sealed_principal_authorizer, id_seed=1000, replay_capacity=2, heartbeat_interval_s=0.05)
        for _ in range(5):
            hub.publish("agent", "agent.step", {}, owner="ui")
        resets = []
        client = RealtimeClient(
            InProcessTransport(hub, principal="ui"),
            channels=("agent",),
            cursor="1001",
            backoff=_backoff(),
            sleep=_no_sleep,
            on_reset=resets.append,
        )
        frames = client.frames()
        (reset,) = await _take(frames, 1)
        assert reset.type == "stream.reset" and resets == [reset]
        assert client.last_event_id == hub.head_id
        client.close()
        await frames.aclose()

    asyncio.run(scenario())


def test_dead_stream_after_silence_triggers_reconnect():
    class SilentTransport:
        name = "silent"

        def __init__(self):
            self.opens = 0

        async def open(self, *, channels, job_id, cursor):
            self.opens += 1
            transport = self

            class Stream:
                retry_ms = None

                async def __aiter__(self):
                    if transport.opens >= 2:
                        yield RealtimeEvent(id="7", ts="2026-10-17T16:00:00.000Z", channel="build", type="build.log")
                    await asyncio.sleep(3600)

                async def aclose(self):
                    return None

            return Stream()

    async def scenario():
        transport = SilentTransport()
        client = RealtimeClient(transport, dead_stream_s=0.05, backoff=_backoff(), sleep=_no_sleep)
        events = client.events()
        (event,) = await _take(events, 1)
        assert event.id == "7"
        assert client.stats["heartbeat_misses"] == 1 and transport.opens == 2
        client.close()
        await events.aclose()

    asyncio.run(scenario())


def test_auth_errors_are_not_retried():
    class Denied:
        name = "denied"

        async def open(self, **_kw):
            raise RealtimeAuthError("nope", status_code=401)

    async def scenario():
        client = RealtimeClient(Denied(), backoff=_backoff(), sleep=_no_sleep)
        with pytest.raises(RealtimeAuthError):
            await client.events().__anext__()
        assert client.stats["connect_attempts"] == 1

    asyncio.run(scenario())


# --------------------------------------------------------------------------
# Real HTTP: uvicorn + gate + /api/v1/events
# --------------------------------------------------------------------------

uvicorn = pytest.importorskip("uvicorn")
httpx = pytest.importorskip("httpx")
fastapi = pytest.importorskip("fastapi")

_SECRET = "realtime-test-" + "seal-key"


@pytest.fixture()
def live_server(monkeypatch):
    from skeleton.api.middleware import GatePolicy, install_gate
    from skeleton.api.realtime_routes import router

    monkeypatch.setenv("GF_SEAL_SECRET", _SECRET)
    hub = RealtimeHub(authorizer=sealed_principal_authorizer, id_seed=500, heartbeat_interval_s=0.1)
    app = fastapi.FastAPI()
    app.state.realtime_hub = hub
    app.include_router(router, prefix="/api/v1")
    install_gate(app, policy=GatePolicy())

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    try:
        yield f"http://127.0.0.1:{port}", hub
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


def _seal_headers():
    from skeleton.api.hmac_seal import mint_seal

    return {"x-gf-seal": mint_seal("ui-tester", secret=_SECRET)}


def test_http_stream_requires_seal(live_server):
    base, _hub = live_server
    resp = httpx.get(base + "/api/v1/events", timeout=5)
    assert resp.status_code == 401


def test_http_connect_publish_drop_reconnect_resume(live_server):
    base, hub = live_server

    async def scenario():
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=None)) as http:
            transport = SSETransport(base, client=http, headers=_seal_headers)
            client = RealtimeClient(transport, channels=("build", "agent"), backoff=_backoff(), sleep=_no_sleep)
            events = client.events()
            pending = asyncio.ensure_future(_take(events, 2, timeout=10))
            first = await _wait_for_sub(hub, timeout=10)
            await asyncio.to_thread(hub.publish, "build", "build.started", {"step": 1}, job_id="job-h", owner="ui-tester")
            await asyncio.to_thread(hub.publish, "agent", "agent.step", {"step": 2}, job_id="job-h", owner="ui-tester")
            got = await pending
            assert [e.type for e in got] == ["build.started", "agent.step"]
            assert [e.id for e in got] == ["501", "502"]
            hub.unsubscribe(first, reason="test_drop")
            hub.publish("build", "build.completed", {"step": 3}, job_id="job-h", owner="ui-tester")
            (resumed,) = await _take(events, 1, timeout=10)
            assert resumed.id == "503" and resumed.type == "build.completed"
            assert client.stats["reconnects"] == 1
            counters = hub.slo.snapshot()["counters"]
            assert counters["resume_attempts"] == 1 and counters["resume_successes"] == 1
            client.close()
            await events.aclose()

    asyncio.run(scenario())


def test_http_heartbeat_comment_and_retry_line(live_server):
    base, _hub = live_server

    async def scenario():
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=5.0)) as http:
            async with http.stream("GET", base + "/api/v1/events", params={"channels": "build"}, headers=_seal_headers()) as resp:
                assert resp.status_code == 200
                assert resp.headers["content-type"].startswith("text/event-stream")
                buf = ""
                async for chunk in resp.aiter_text():
                    buf += chunk
                    if ": hb" in buf:
                        break
                assert buf.startswith("retry: ")
                assert ": hb" in buf

    asyncio.run(scenario())


def test_http_presence_join_and_snapshot(live_server):
    base, hub = live_server
    headers = _seal_headers()
    resp = httpx.post(base + "/api/v1/presence", json={"action": "join", "client_id": "tab-1", "scope": "proj-1"}, headers=headers, timeout=5)
    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == 1
    snap = httpx.get(base + "/api/v1/presence", params={"scope": "proj-1"}, headers=_seal_headers(), timeout=5).json()
    assert [m["client_id"] for m in snap["members"]] == ["tab-1"]
    bad = httpx.post(base + "/api/v1/presence", json={"action": "teleport", "client_id": "tab-1"}, headers=_seal_headers(), timeout=5)
    assert bad.status_code == 422
    left = httpx.post(base + "/api/v1/presence", json={"action": "leave", "client_id": "tab-1", "scope": "proj-1"}, headers=_seal_headers(), timeout=5)
    assert left.json()["count"] == 0
    types = [e.type for e in hub._ring]
    assert types == ["presence.joined", "presence.left"]
