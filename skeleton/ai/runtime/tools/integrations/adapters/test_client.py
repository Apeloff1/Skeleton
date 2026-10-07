"""Tests for ModelClient: retries, breakers, deadlines, fallback, streaming."""

from __future__ import annotations

import asyncio
import random

import pytest

from .circuit import CircuitBreakerConfig, CircuitState
from .client import ClientConfig, ModelClient
from .deadline import CancellationToken, Deadline, ManualClock
from .errors import (
    AuthenticationError,
    CapabilityDeniedError,
    IntegrationError,
    InvalidRequestError,
    NoProviderAvailableError,
    OperationCancelledError,
    ProviderNotFoundError,
    ProviderUnavailableError,
)
from .fakes import ScriptedProvider
from .observe import EventLog, MetricsRecorder, ObserverHub
from .offline import OfflineProvider
from .registry import ProviderRegistry, SelectionPolicy
from .retry import Jitter, RetryPolicy
from .types import ChatRequest, ChunkKind, ProviderCapability, StreamChunk, ToolSpec

FAST_RETRY = RetryPolicy(max_attempts=3, base_delay=0.01, max_delay=0.01, jitter=Jitter.NONE)


def build(*providers, fallback: bool = True, config: ClientConfig | None = None, log: EventLog | None = None):
    reg = ProviderRegistry()
    for p in providers:
        reg.register(p)
    if fallback:
        reg.register(OfflineProvider(), fallback=True)
    hub = ObserverHub([log] if log else [])
    cfg = config or ClientConfig(retry=FAST_RETRY, attempt_timeout=1.0, total_timeout=5.0)
    return ModelClient(reg, cfg, clock=ManualClock(), observers=hub, rng=random.Random(0))


def run(coro):
    return asyncio.run(coro)


REQ = ChatRequest.from_prompt("hello world")


def test_config_validation():
    with pytest.raises(ValueError):
        ClientConfig(attempt_timeout=0)
    with pytest.raises(ValueError):
        ClientConfig(fallback_grace=-1)
    with pytest.raises(ValueError):
        ClientConfig(max_concurrency=0)


def test_primary_success_no_fallback():
    primary = ScriptedProvider("primary", ["hi there"])
    client = build(primary)
    resp = run(client.complete(REQ))
    assert resp.text == "hi there" and resp.provider == "primary"
    assert not resp.fallback_used and resp.attempts == 1
    assert resp.metadata["tried"] == ["primary"]
    assert len(resp.metadata["trace_id"]) == 16


def test_retries_transient_failure_on_same_provider():
    primary = ScriptedProvider("primary", [ProviderUnavailableError("blip"), "recovered"])
    log = EventLog()
    client = build(primary, log=log)
    resp = run(client.complete(REQ))
    assert resp.text == "recovered" and resp.attempts == 2 and not resp.fallback_used
    assert "retry_scheduled" in log.kinds()
    assert [c.attempt for c in primary.contexts] == [1, 2]


def test_falls_over_to_next_provider_then_offline():
    a = ScriptedProvider("a", [ProviderUnavailableError("down")], priority=1)
    b = ScriptedProvider("b", [AuthenticationError("bad key")], priority=2)
    log = EventLog()
    client = build(a, b, log=log)
    resp = run(client.complete(REQ))
    assert resp.provider == "offline" and resp.fallback_used
    assert resp.metadata["tried"] == ["a", "b", "offline"]
    assert len(a.calls) == 3  # retried
    assert len(b.calls) == 1  # auth is not retried
    assert log.of_kind("fallback_served")[0].attributes["skipped"] == ["a", "b"]


def test_runs_with_no_remote_providers_at_all():
    client = build()
    assert run(client.ask("what is 2+3")) == "2+3 = 5"


def test_terminal_caller_errors_stop_the_walk():
    for err in (InvalidRequestError("bad"), CapabilityDeniedError("no"), OperationCancelledError("x")):
        p = ScriptedProvider("p", [err])
        client = build(p)
        with pytest.raises(type(err)):
            run(client.complete(REQ))


def test_no_candidates_raises():
    reg = ProviderRegistry()
    reg.register(ScriptedProvider("chat", ["x"], capabilities=frozenset({ProviderCapability.CHAT})))
    client = ModelClient(reg, clock=ManualClock())
    with pytest.raises(NoProviderAvailableError):
        run(client.complete(ChatRequest.from_prompt("x", required_capabilities=frozenset({"vision"}))))


def test_all_fail_without_fallback_reports_failures():
    a = ScriptedProvider("a", [ProviderUnavailableError("down")])
    client = build(a, fallback=False)
    with pytest.raises(NoProviderAvailableError) as info:
        run(client.complete(REQ))
    assert set(info.value.failures) == {"a"}
    assert info.value.failures["a"].code == "retry_exhausted"


def test_attempt_timeout_triggers_retry_then_fallback():
    slow = ScriptedProvider("slow", [("sleep", 5)])
    cfg = ClientConfig(retry=RetryPolicy(max_attempts=2, base_delay=0, max_delay=0), attempt_timeout=0.02)
    client = build(slow, config=cfg)
    resp = run(client.complete(REQ))
    assert resp.provider == "offline"
    assert len(slow.calls) == 2


def test_circuit_opens_and_skips_provider():
    flaky = ScriptedProvider("flaky", [ProviderUnavailableError("down")])
    cfg = ClientConfig(
        retry=RetryPolicy(max_attempts=1, base_delay=0, max_delay=0),
        breaker=CircuitBreakerConfig(failure_threshold=2, reset_timeout=60),
    )
    log = EventLog()
    client = build(flaky, config=cfg, log=log)
    for _ in range(2):
        run(client.complete(REQ))
    assert client.breakers.get("flaky").state is CircuitState.OPEN
    calls_before = len(flaky.calls)
    resp = run(client.complete(REQ))
    assert resp.provider == "offline"
    assert len(flaky.calls) == calls_before  # failed fast, provider untouched
    assert any(e.attributes.get("to") == "open" for e in log.of_kind("circuit_transition"))


def test_circuit_half_open_recovery():
    p = ScriptedProvider("p", [ProviderUnavailableError(), "back"])
    cfg = ClientConfig(
        retry=RetryPolicy(max_attempts=1, base_delay=0, max_delay=0),
        breaker=CircuitBreakerConfig(failure_threshold=1, reset_timeout=10),
    )
    client = build(p, config=cfg)
    run(client.complete(REQ))
    assert client.breakers.get("p").state is CircuitState.OPEN
    client.clock.advance(10)  # type: ignore[attr-defined]
    resp = run(client.complete(REQ))
    assert resp.provider == "p" and resp.text == "back"
    assert client.breakers.get("p").state is CircuitState.CLOSED


def test_expired_deadline_still_served_by_fallback_grace():
    clock = ManualClock()
    p = ScriptedProvider("p", ["never"])
    reg = ProviderRegistry()
    reg.register(p)
    reg.register(OfflineProvider(), fallback=True)
    client = ModelClient(reg, ClientConfig(fallback_grace=1.0), clock=clock)
    dl = Deadline.after(1.0, clock)
    clock.advance(2)
    resp = run(client.complete(REQ, deadline=dl))
    assert resp.provider == "offline" and resp.fallback_used
    assert p.calls == []


def test_no_grace_means_deadline_error_surface():
    clock = ManualClock()
    reg = ProviderRegistry()
    reg.register(OfflineProvider(), fallback=True)
    client = ModelClient(reg, ClientConfig(fallback_grace=0), clock=clock)
    dl = Deadline.after(1.0, clock)
    clock.advance(2)
    with pytest.raises(NoProviderAvailableError) as info:
        run(client.complete(REQ, deadline=dl))
    assert info.value.failures["offline"].code == "deadline_exceeded"


def test_cancel_token_before_call():
    token = CancellationToken()
    token.cancel("stop")
    client = build(ScriptedProvider("p", ["x"]))
    with pytest.raises(OperationCancelledError):
        run(client.complete(REQ, token=token))


def test_explicit_provider_pin_with_fallback():
    a = ScriptedProvider("a", ["from a"], priority=1)
    b = ScriptedProvider("b", [ProviderUnavailableError()], priority=2)
    client = build(a, b)
    assert client.plan(REQ, provider="b") == ["b", "offline"]
    resp = run(client.complete(REQ, provider="b"))
    assert resp.provider == "offline"
    assert a.calls == []
    with pytest.raises(ProviderNotFoundError):
        client.plan(REQ, provider="zzz")


def test_model_routing_uses_provider_default():
    p = ScriptedProvider("p", ["ok"], models=("p-large", "p-small"))
    client = build(p)
    run(client.complete(REQ))
    assert p.calls[0].model == "p-large"
    run(client.complete(REQ.with_model("p-small")))
    assert p.calls[1].model == "p-small"


def test_tools_request_skips_toolless_provider_but_offline_can_route():
    chat_only = ScriptedProvider("chat", ["x"], capabilities=frozenset({ProviderCapability.CHAT}))
    client = build(chat_only)
    req = ChatRequest.from_prompt("/clock", tools=(ToolSpec("clock"),))
    resp = run(client.complete(req))
    assert resp.provider == "offline" and resp.tool_calls[0].name == "clock"


def test_selection_policy_local_only():
    cloud = ScriptedProvider("cloud", ["cloud"], priority=1)
    client = build(cloud)
    resp = run(client.complete(REQ, policy=SelectionPolicy(local_only=True)))
    assert resp.provider == "offline"


def test_metrics_recorder_counts_attempts():
    metrics = MetricsRecorder()
    reg = ProviderRegistry()
    reg.register(ScriptedProvider("p", [ProviderUnavailableError(), "ok"]))
    client = ModelClient(reg, ClientConfig(retry=FAST_RETRY), clock=ManualClock(), observers=ObserverHub([metrics]))
    run(client.complete(REQ))
    assert metrics.count("attempt_failed", "p", "provider_unavailable") == 1
    assert metrics.count("attempt_succeeded", "p") == 1


def test_concurrent_calls_are_bounded():
    active = {"now": 0, "peak": 0}

    class Gauge(ScriptedProvider):
        async def _complete(self, request, ctx):
            active["now"] += 1
            active["peak"] = max(active["peak"], active["now"])
            await asyncio.sleep(0.01)
            active["now"] -= 1
            return await super()._complete(request, ctx)

    reg = ProviderRegistry()
    reg.register(Gauge("g", ["ok"]))

    async def main():
        client = ModelClient(reg, ClientConfig(max_concurrency=2), clock=ManualClock())
        await asyncio.gather(*(client.complete(REQ) for _ in range(6)))

    run(main())
    assert active["peak"] <= 2


# -- streaming ---------------------------------------------------------------


async def collect(client, request, **kw):
    return [c async for c in client.stream(request, **kw)]


def test_stream_happy_path_reindexes_and_tags_provider():
    chunks = [StreamChunk.text_delta(5, "a"), StreamChunk.text_delta(9, "b"), StreamChunk.finish(11)]
    p = ScriptedProvider("p", [("stream", chunks)])
    client = build(p)
    out = run(collect(client, REQ))
    assert [c.index for c in out] == [0, 1, 2]
    assert all(c.provider == "p" for c in out)


def test_stream_fails_over_before_first_chunk():
    p = ScriptedProvider("p", [("stream", [StreamChunk.text_delta(0, "x")], (0, ProviderUnavailableError()))])
    log = EventLog()
    client = build(p, log=log)
    out = run(collect(client, REQ))
    assert out[-1].kind is ChunkKind.FINISH
    assert all(c.provider == "offline" for c in out)
    assert "stream_open_failed" in log.kinds()


def test_stream_retries_same_provider_before_output():
    good = [StreamChunk.text_delta(0, "ok"), StreamChunk.finish(1)]
    p = ScriptedProvider(
        "p",
        [("stream", [StreamChunk.text_delta(0, "x")], (0, ProviderUnavailableError())), ("stream", good)],
    )
    client = build(p)
    out = run(collect(client, REQ))
    assert "".join(c.text for c in out) == "ok" and out[0].provider == "p"


def test_stream_mid_failure_is_surfaced_not_replayed():
    chunks = [StreamChunk.text_delta(0, "par"), StreamChunk.text_delta(1, "tial")]
    p = ScriptedProvider("p", [("stream", chunks, (1, ProviderUnavailableError("cut")))])
    log = EventLog()
    client = build(p, log=log)
    seen: list[str] = []

    async def main():
        async for chunk in client.stream(REQ):
            seen.append(chunk.text)

    with pytest.raises(IntegrationError) as info:
        run(main())
    assert info.value.code == "provider_unavailable"
    assert seen == ["par"]
    assert "stream_broken" in log.kinds()


def test_stream_terminal_error_raised():
    p = ScriptedProvider("p", [("stream", [], (0, InvalidRequestError("bad")))])
    client = build(p)
    with pytest.raises(InvalidRequestError):
        run(collect(client, REQ))


def test_stream_empty_stream_falls_back():
    p = ScriptedProvider("p", [("stream", [])])
    client = build(p)
    out = run(collect(client, REQ))
    assert out[0].provider == "offline"


def test_stream_idle_timeout_falls_back():
    class Stall(ScriptedProvider):
        async def stream(self, request, ctx):
            await asyncio.sleep(5)
            yield StreamChunk.text_delta(0, "late")

    cfg = ClientConfig(retry=RetryPolicy(max_attempts=1, base_delay=0, max_delay=0), stream_idle_timeout=0.02)
    client = build(Stall("stall", ["x"]), config=cfg)
    out = run(collect(client, REQ))
    assert out[0].provider == "offline"


def test_stream_early_consumer_exit_closes_cleanly():
    chunks = [StreamChunk.text_delta(i, str(i)) for i in range(10)] + [StreamChunk.finish(10)]
    p = ScriptedProvider("p", [("stream", chunks)])
    client = build(p)

    async def main():
        agen = client.stream(REQ)
        first = await agen.__anext__()
        await agen.aclose()
        return first

    assert run(main()).text == "0"
    assert client.breakers.get("p").state is CircuitState.CLOSED


def test_stream_to_response_and_no_fallback_failure():
    client = build(ScriptedProvider("p", ["whole answer"]))
    resp = run(client.stream_to_response(REQ))
    assert resp.text == "whole answer"
    dead = build(ScriptedProvider("p", [("stream", [], (0, ProviderUnavailableError()))]), fallback=False)
    with pytest.raises(NoProviderAvailableError):
        run(collect(dead, REQ))


def test_health_and_snapshot():
    client = build(ScriptedProvider("p", ["x"], healthy=False))
    health = run(client.health())
    assert health["p"]["healthy"] is False and health["offline"]["healthy"] is True
    assert health["p"]["circuit"] == "closed"
    snap = client.snapshot()
    assert snap["registry"]["fallback"] == "offline"
