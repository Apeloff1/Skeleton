"""Realtime SDK follow-up to #4128 (Coder Lead #4136 review).

* typed connect errors carry ``status_code`` / ``error_code`` / ``retryable``;
* 503 ``seal_unavailable`` is raised immediately, never retried (frozen seal
  contract); ``invalid_seal`` and ``seal_required`` are distinguishable;
* abandoning a stream closes the body iterator (no "never awaited" warning);
* reconnect sends ``?cursor=`` alongside ``Last-Event-ID``.
"""

from __future__ import annotations

import asyncio
import gc
import json
import socket
import threading
import time
import warnings

import pytest

from skeleton.client.realtime import (
    RealtimeAuthError,
    RealtimeClient,
    RealtimeConnectError,
    RealtimeError,
    RealtimeSealUnavailable,
    ReconnectBackoff,
    SSETransport,
)
from skeleton.client.realtime.transport import ERROR_BODY_LIMIT, _SSEStream
from skeleton.realtime.envelope import RealtimeEvent
from skeleton.realtime.sse import SSE_MEDIA_TYPE, format_retry, format_sse_event

httpx = pytest.importorskip("httpx")

_FAKE_SEAL = "test-only-" + "not-a-real-seal"


def _backoff():
    return ReconnectBackoff(rng=lambda lo, hi: 0.0)


class _Sleeps:
    def __init__(self):
        self.calls = []

    async def __call__(self, delay):
        self.calls.append(delay)
        await asyncio.sleep(0)


def _mock_transport(handler, **kw):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return http, SSETransport("http://rt.test", client=http, headers=lambda: {"x-gf-seal": _FAKE_SEAL}, **kw)


async def _open_error(handler):
    http, transport = _mock_transport(handler)
    try:
        with pytest.raises(RealtimeError) as info:
            await transport.open(channels=("build",), job_id=None, cursor=None)
        return info.value
    finally:
        await http.aclose()


# --------------------------------------------------------------------------
# error bodies -> typed errors
# --------------------------------------------------------------------------


def test_seal_unavailable_raised_immediately_with_zero_retries():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503, json={"error": "seal_unavailable"})

    async def scenario():
        http, transport = _mock_transport(handler)
        sleeps = _Sleeps()
        client = RealtimeClient(transport, backoff=_backoff(), sleep=sleeps)
        with pytest.raises(RealtimeSealUnavailable) as info:
            await client.events().__anext__()
        await http.aclose()
        return client, sleeps, info.value

    client, sleeps, err = asyncio.run(scenario())
    assert len(calls) == 1
    assert sleeps.calls == []
    assert client.stats["connect_attempts"] == 1
    assert client.backoff.attempt == 0
    assert err.status_code == 503 and err.error_code == "seal_unavailable"
    assert err.retryable is False
    assert not isinstance(err, RealtimeConnectError)


def test_invalid_seal_and_seal_required_have_distinct_codes():
    async def scenario():
        invalid = await _open_error(lambda r: httpx.Response(401, json={"error": "invalid_seal"}))
        # FastAPI HTTPException shape used by realtime_routes._principal.
        required = await _open_error(lambda r: httpx.Response(401, json={"detail": {"error": "seal_required"}}))
        return invalid, required

    invalid, required = asyncio.run(scenario())
    assert isinstance(invalid, RealtimeAuthError) and isinstance(required, RealtimeAuthError)
    assert invalid.status_code == required.status_code == 401
    assert invalid.error_code == "invalid_seal"
    assert required.error_code == "seal_required"
    assert invalid.retryable is False and required.retryable is False


def test_error_message_never_contains_seal_or_body_text():
    secretish = "sk-" + "deadbeef" * 8

    async def scenario():
        echoed = await _open_error(
            lambda r: httpx.Response(401, json={"error": r.headers["x-gf-seal"], "detail": secretish})
        )
        freeform = await _open_error(lambda r: httpx.Response(500, text=f"boom {secretish} {_FAKE_SEAL}"))
        # A snake_case-shaped value we sent is still never echoed back.
        http, transport = _mock_transport(lambda r: httpx.Response(401, json={"error": r.headers["x-gf-seal"]}))
        transport._headers = lambda: {"x-gf-seal": "abc_secret_seal"}
        with pytest.raises(RealtimeAuthError) as info:
            await transport.open(channels=("build",), job_id=None, cursor=None)
        await http.aclose()
        return echoed, freeform, info.value

    echoed, freeform, snake = asyncio.run(scenario())
    assert "abc_secret_seal" not in str(snake) and snake.error_code is None
    for err in (echoed, freeform):
        assert _FAKE_SEAL not in str(err) and secretish not in str(err)
        assert err.error_code is None
    assert freeform.retryable is True and freeform.status_code == 500


def test_error_body_read_is_bounded():
    served = []

    async def body():
        for _ in range(64):
            served.append(1)
            yield b"x" * 1024

    async def scenario():
        return await _open_error(lambda r: httpx.Response(502, content=body()))

    err = asyncio.run(scenario())
    assert isinstance(err, RealtimeConnectError) and err.status_code == 502
    assert len(served) * 1024 <= ERROR_BODY_LIMIT + 1024


def test_retryable_semantics_by_status():
    async def scenario():
        transient = await _open_error(lambda r: httpx.Response(503, json={"detail": {"error": "realtime_unavailable"}}))
        permanent = await _open_error(lambda r: httpx.Response(422, json={"detail": {"error": "unknown_channel"}}))
        forbidden = await _open_error(lambda r: httpx.Response(403, json={"detail": {"error": "channel_forbidden"}}))
        return transient, permanent, forbidden

    transient, permanent, forbidden = asyncio.run(scenario())
    assert type(transient) is RealtimeConnectError and transient.retryable is True
    assert transient.error_code == "realtime_unavailable"
    assert type(permanent) is RealtimeConnectError and permanent.retryable is False
    assert permanent.error_code == "unknown_channel"
    assert isinstance(forbidden, RealtimeAuthError) and forbidden.error_code == "channel_forbidden"


def test_non_retryable_connect_error_is_not_backed_off():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(422, json={"detail": {"error": "unknown_channel"}})

    async def scenario():
        http, transport = _mock_transport(handler)
        sleeps = _Sleeps()
        client = RealtimeClient(transport, backoff=_backoff(), sleep=sleeps)
        with pytest.raises(RealtimeConnectError):
            await client.events().__anext__()
        await http.aclose()
        return sleeps

    sleeps = asyncio.run(scenario())
    assert len(calls) == 1 and sleeps.calls == []


def test_realtime_unavailable_503_is_still_retried():
    calls = []
    event = RealtimeEvent(id="9", ts="2026-10-17T16:00:00.000Z", channel="build", type="build.log")

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(503, json={"detail": {"error": "realtime_unavailable"}})
        return httpx.Response(200, headers={"content-type": SSE_MEDIA_TYPE}, text=format_sse_event(event))

    async def scenario():
        http, transport = _mock_transport(handler)
        sleeps = _Sleeps()
        client = RealtimeClient(transport, backoff=_backoff(), sleep=sleeps)
        events = client.events()
        got = await events.__anext__()
        client.close()
        await events.aclose()
        await http.aclose()
        return got, sleeps

    got, sleeps = asyncio.run(scenario())
    assert got.id == "9" and len(calls) == 3 and len(sleeps.calls) == 2


# --------------------------------------------------------------------------
# stream cleanup
# --------------------------------------------------------------------------


class _TrackedResponse:
    def __init__(self, chunks):
        self.chunks = chunks
        self.body_closed = False

    async def aiter_text(self):
        try:
            for chunk in self.chunks:
                yield chunk
            await asyncio.sleep(3600)
        finally:
            self.body_closed = True


class _Ctx:
    def __init__(self):
        self.exited = 0

    async def __aexit__(self, *exc):
        self.exited += 1


def test_sse_stream_aclose_closes_body_iterator():
    event = RealtimeEvent(id="1", ts="2026-10-17T16:00:00.000Z", channel="build", type="build.log")

    async def scenario():
        resp, ctx = _TrackedResponse([format_retry(1000), format_sse_event(event)]), _Ctx()
        stream = _SSEStream(ctx, resp)
        it = stream.__aiter__()
        items = [await it.__anext__(), await it.__anext__()]
        # Abandon the frame iterator without closing it, then close the stream.
        await stream.aclose()
        await stream.aclose()  # idempotent
        return resp, ctx, items

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        resp, ctx, items = asyncio.run(scenario())
        gc.collect()
    assert resp.body_closed is True and ctx.exited == 1
    assert any(isinstance(i, RealtimeEvent) for i in items)
    assert not [w for w in caught if "never awaited" in str(w.message)]


def test_abandoned_client_generator_closes_stream():
    event = RealtimeEvent(id="5", ts="2026-10-17T16:00:00.000Z", channel="build", type="build.log")
    opened = []

    class Transport:
        name = "tracked"

        async def open(self, *, channels, job_id, cursor):
            resp, ctx = _TrackedResponse([format_sse_event(event)]), _Ctx()
            opened.append((resp, ctx))
            return _SSEStream(ctx, resp)

    async def scenario():
        client = RealtimeClient(Transport(), backoff=_backoff(), sleep=_Sleeps())
        # ``break`` out of the consumer loop, then aclose the generator.
        events = client.events()
        async for got in events:
            assert got.id == "5"
            break
        await events.aclose()

        # Abandon a second generator without closing it at all; asyncio's
        # asyncgen finaliser must still run the cleanup without warnings.
        client2 = RealtimeClient(Transport(), backoff=_backoff(), sleep=_Sleeps())
        abandoned = client2.events()
        await abandoned.__anext__()
        del abandoned
        gc.collect()
        await asyncio.sleep(0.05)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        asyncio.run(scenario())
        gc.collect()
    assert len(opened) == 2
    for resp, ctx in opened:
        assert resp.body_closed is True and ctx.exited == 1
    assert not [w for w in caught if "never awaited" in str(w.message)]


def test_http_abandoned_stream_has_no_never_awaited_warning(live_server):
    base, hub = live_server

    async def scenario():
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=None)) as http:
            client = RealtimeClient(SSETransport(base, client=http, headers=_seal_headers), channels=("build",))
            events = client.events()
            pending = asyncio.ensure_future(asyncio.wait_for(events.__anext__(), 10))
            await _wait_for_sub(hub)
            await asyncio.to_thread(hub.publish, "build", "build.started", {"step": 1})
            got = await pending
            await events.aclose()
            return got

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        got = asyncio.run(scenario())
        gc.collect()
    assert got.type == "build.started"
    assert not [w for w in caught if "never awaited" in str(w.message)]


# --------------------------------------------------------------------------
# ?cursor= resume
# --------------------------------------------------------------------------


def test_engine_job_scope_is_encoded_as_query_params_without_overwriting_filters():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, headers={"content-type": SSE_MEDIA_TYPE}, text=": hb\n\n")

    async def scenario():
        http, transport = _mock_transport(
            handler, actor_id="actor&name", tenant_id="tenant / 2"
        )
        stream = await transport.open(
            channels=("build", "agent"), job_id="job-1", cursor="41"
        )
        await stream.aclose()
        await http.aclose()

    asyncio.run(scenario())
    assert len(seen) == 1
    params = seen[0].url.params
    assert params["channels"] == "build,agent"
    assert params["job_id"] == "job-1"
    assert params["actor_id"] == "actor&name"
    assert params["tenant_id"] == "tenant / 2"
    assert params["cursor"] == "41"
    assert seen[0].headers["last-event-id"] == "41"


def test_engine_scope_must_be_complete_and_bounded():
    with pytest.raises(ValueError, match="supplied together"):
        SSETransport("http://rt.test", actor_id="alice")
    with pytest.raises(ValueError, match="invalid actor/tenant"):
        SSETransport("http://rt.test", actor_id="", tenant_id="t1")
    with pytest.raises(ValueError, match="invalid actor/tenant"):
        SSETransport("http://rt.test", actor_id="alice", tenant_id="t" * 513)


def test_reconnect_sends_cursor_param_and_last_event_id():
    seen = []
    events = [
        RealtimeEvent(id=str(i), ts="2026-10-17T16:00:00.000Z", channel="build", type="build.log") for i in (41, 42)
    ]

    def handler(request):
        seen.append((dict(request.url.params), request.headers.get("last-event-id")))
        body = format_sse_event(events[min(len(seen) - 1, 1)])
        return httpx.Response(200, headers={"content-type": SSE_MEDIA_TYPE}, text=body)

    async def scenario():
        http, transport = _mock_transport(handler)
        client = RealtimeClient(transport, channels=("build",), backoff=_backoff(), sleep=_Sleeps())
        gen = client.events()
        got = [await gen.__anext__(), await gen.__anext__()]
        client.close()
        await gen.aclose()
        await http.aclose()
        return got

    got = asyncio.run(scenario())
    assert [e.id for e in got] == ["41", "42"]
    first_params, first_header = seen[0]
    assert "cursor" not in first_params and first_header is None
    second_params, second_header = seen[1]
    assert second_params["cursor"] == "41" and second_header == "41"
    assert second_params["channels"] == "build"


def test_http_cursor_param_alone_resumes(live_server):
    base, hub = live_server
    for i in range(3):
        hub.publish("build", "build.log", {"i": i})

    async def scenario():
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=5.0)) as http:
            async with http.stream(
                "GET", base + "/api/v1/events", params={"channels": "build", "cursor": "501"}, headers=_seal_headers()
            ) as resp:
                assert resp.status_code == 200
                buf = ""
                async for chunk in resp.aiter_text():
                    buf += chunk
                    if "id: 503" in buf:
                        break
                return buf

    buf = asyncio.run(scenario())
    assert "id: 501\n" not in buf and "id: 502" in buf and "id: 503" in buf


# --------------------------------------------------------------------------
# Real HTTP gate: seal codes end to end
# --------------------------------------------------------------------------

uvicorn = pytest.importorskip("uvicorn")
fastapi = pytest.importorskip("fastapi")

_SECRET = "realtime-errors-" + "seal-key"


def _serve(app):
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
    return f"http://127.0.0.1:{port}", server, thread, sock


def _app(hub, *, gate=True):
    from skeleton.api.middleware import GatePolicy, install_gate
    from skeleton.api.realtime_routes import router

    app = fastapi.FastAPI()
    app.state.realtime_hub = hub
    app.include_router(router, prefix="/api/v1")
    if gate:
        install_gate(app, policy=GatePolicy())
    return app


@pytest.fixture()
def live_server(monkeypatch):
    from skeleton.realtime import RealtimeHub

    monkeypatch.setenv("GF_SEAL_SECRET", _SECRET)
    hub = RealtimeHub(id_seed=500, heartbeat_interval_s=0.1)
    base, server, thread, sock = _serve(_app(hub))
    try:
        yield base, hub
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


def _seal_headers():
    from skeleton.api.hmac_seal import mint_seal

    return {"x-gf-seal": mint_seal("ui-tester", secret=_SECRET)}


async def _wait_for_sub(hub, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with hub._lock:
            if hub._subs:
                return
        await asyncio.sleep(0.01)
    raise AssertionError("no subscriber connected")


def _http_open_error(base, headers):
    async def scenario():
        async with httpx.AsyncClient(timeout=5.0) as http:
            transport = SSETransport(base, client=http, headers=lambda: dict(headers))
            with pytest.raises(RealtimeError) as info:
                await transport.open(channels=("build",), job_id=None, cursor=None)
            return info.value

    return asyncio.run(scenario())


def test_http_gate_invalid_seal_code(live_server):
    base, _hub = live_server
    err = _http_open_error(base, {"x-gf-seal": _FAKE_SEAL})
    assert isinstance(err, RealtimeAuthError)
    assert err.status_code == 401 and err.error_code == "invalid_seal"
    assert _FAKE_SEAL not in str(err)


def test_http_gate_seal_unavailable_never_retried(monkeypatch):
    from skeleton.realtime import RealtimeHub

    monkeypatch.delenv("GF_SEAL_SECRET", raising=False)
    monkeypatch.delenv("GF_SEAL_KEYRING", raising=False)
    base, server, thread, sock = _serve(_app(RealtimeHub(id_seed=0)))
    try:
        probe = httpx.get(base + "/api/v1/events", timeout=5)
        if probe.status_code != 503:
            pytest.skip(f"seal secret resolved from environment ({probe.status_code})")
        assert json.loads(probe.text) == {"error": "seal_unavailable"}

        async def scenario():
            async with httpx.AsyncClient(timeout=5.0) as http:
                sleeps = _Sleeps()
                client = RealtimeClient(SSETransport(base, client=http), backoff=_backoff(), sleep=sleeps)
                with pytest.raises(RealtimeSealUnavailable) as info:
                    await client.events().__anext__()
                return client, sleeps, info.value

        client, sleeps, err = asyncio.run(scenario())
        assert client.stats["connect_attempts"] == 1 and sleeps.calls == []
        assert err.status_code == 503 and err.retryable is False
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


def test_http_route_seal_required_code_without_gate():
    from skeleton.realtime import RealtimeHub

    base, server, thread, sock = _serve(_app(RealtimeHub(id_seed=0), gate=False))
    try:
        err = _http_open_error(base, {})
        assert isinstance(err, RealtimeAuthError)
        assert err.status_code == 401 and err.error_code == "seal_required"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
