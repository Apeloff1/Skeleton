"""#4122: events.stream_realtime uses #4140's typed errors, not the #4136 bare-401 workaround."""

from __future__ import annotations

import httpx
import pytest

from skeleton.client import BuildsClient, GatewayClient, RequestSealer, RetryPolicy, SkeletonSealConfigError
from skeleton.client import events as events_mod
from skeleton.client.realtime import RealtimeAuthError, RealtimeSealUnavailable, ReconnectBackoff

SECRET = "wire-test-secret-4122"


async def _no_sleep(_d):
    return None


def _opts():
    return {"backoff": ReconnectBackoff(rng=lambda lo, hi: 0.0), "sleep": _no_sleep}


def _gw(seal=None):
    return GatewayClient(
        "http://test",
        client=httpx.Client(base_url="http://test", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))),
        retry=RetryPolicy(max_attempts=2, base_delay_seconds=0.01, max_delay_seconds=0.02),
        sleep=lambda s: None, seal=seal,
    )


def _ac(handler):
    async def ah(req):
        return handler(req)
    return httpx.AsyncClient(transport=httpx.MockTransport(ah))


def _run(handler, seal):
    return list(BuildsClient(_gw(seal), actor_id="u", tenant_id="t").stream_events(
        "e1", http_client=_ac(handler), realtime_options=_opts()))


def test_should_remint_dispatches_on_error_code():
    f = events_mod._should_remint
    assert f(RealtimeAuthError("x", status_code=401, error_code="invalid_seal"))
    assert f(RealtimeAuthError("x", status_code=401, error_code=None))  # legacy body
    assert not f(RealtimeAuthError("x", status_code=401, error_code="seal_required"))
    assert not f(RealtimeAuthError("x", status_code=403, error_code="channel_forbidden"))
    assert not f(ValueError("x"))


def test_seal_required_401_is_not_reminted(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    hits = []

    def handler(req):
        hits.append(1)
        return httpx.Response(401, json={"error": "seal_required"})

    with pytest.raises(RealtimeAuthError) as ei:
        _run(handler, RequestSealer("sdk-test"))
    assert ei.value.error_code == "seal_required" and hits == [1]


def test_seal_unavailable_503_raises_config_error_without_retry(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    hits = []

    def handler(req):
        hits.append(1)
        return httpx.Response(503, json={"error": "seal_unavailable"})

    with pytest.raises(SkeletonSealConfigError) as ei:
        _run(handler, RequestSealer("sdk-test"))
    assert isinstance(ei.value.__cause__, RealtimeSealUnavailable)
    assert hits == [1]


def test_cursor_resume_uses_4140_query_param():
    from skeleton.realtime.envelope import RealtimeEvent
    from skeleton.realtime.sse import format_sse

    seen = []
    ev = RealtimeEvent(id="5", ts="2026-10-24T20:00:00.000Z", channel="build",
                       type="build.progress", payload={}, job_id="e1")

    def handler(req):
        seen.append(req)
        body = ": hb\n\n" + format_sse(ev)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())

    gen = BuildsClient(_gw(), actor_id="u", tenant_id="t").stream_events(
        "e1", cursor="4", http_client=_ac(handler), realtime_options=_opts())
    first = next(gen)
    gen.close()
    assert first.id == "5"
    assert seen[0].headers["last-event-id"] == "4" and seen[0].url.params["cursor"] == "4"
