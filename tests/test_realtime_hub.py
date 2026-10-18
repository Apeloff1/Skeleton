"""Realtime hub: fan-out, replay/resume, backpressure, presence, secret guard, SLO."""

from __future__ import annotations

import asyncio
import threading

import pytest

from skeleton.observability import MetricsCollector
from skeleton.realtime import (
    HubJobEventSink,
    NullJobEventPublisher,
    PayloadSecretGuard,
    RealtimeAuthError,
    RealtimeHub,
    RealtimeSecretError,
    attach_hub,
)
from skeleton.realtime.envelope import ControlEvent, RealtimeEvent
from skeleton.realtime.hub import sealed_principal_authorizer
from skeleton.realtime.sinks import JobEventPublisher


def _hub(**kw):
    kw.setdefault("id_seed", 1000)
    kw.setdefault("authorizer", sealed_principal_authorizer)
    return RealtimeHub(**kw)


def _events(frames):
    return [f for f in frames if isinstance(f, RealtimeEvent) and f.type != "presence.snapshot"]


def test_single_monotonic_stream_across_channels():
    hub = _hub()
    a = hub.publish("build", "build.started", {"n": 1}, job_id="job-1", owner="p")
    b = hub.publish("agent", "agent.step", {"n": 2}, owner="p")
    c = hub.publish("build", "build.progress", {"n": 3}, job_id="job-1", owner="p")
    assert [a.id, b.id, c.id] == ["1001", "1002", "1003"]
    assert hub.head_id == "1003"


def test_ids_survive_restart_by_seeding_from_wall_clock():
    first = RealtimeHub()
    second = RealtimeHub()
    assert int(second.head_id) >= int(first.head_id)
    assert int(first.head_id) > 10**15


def test_fanout_respects_channels_and_job_filter():
    hub = _hub()
    builds = hub.subscribe(["build"], principal="p")
    job = hub.subscribe(["build", "agent"], principal="p", job_id="job-2")
    hub.publish("build", "build.log", {"line": "a"}, job_id="job-1", owner="p")
    hub.publish("agent", "agent.step", {"s": 1}, job_id="job-2", owner="p")
    hub.publish("build", "build.log", {"line": "b"}, job_id="job-2", owner="p")
    assert [e.payload for e in _events(builds.drain())] == [{"line": "a"}, {"line": "b"}]
    assert [e.type for e in _events(job.drain())] == ["agent.step", "build.log"]


def test_resume_replays_missed_events_after_cursor():
    hub = _hub()
    ids = [hub.publish("build", "build.progress", {"i": i}, owner="p").id for i in range(5)]
    sub = hub.subscribe(["build"], principal="p", cursor=int(ids[1]))
    assert [e.id for e in _events(sub.drain())] == ids[2:]
    assert sub.replayed == 3
    snap = hub.slo.snapshot()
    assert snap["counters"]["events_resumed"] == 3
    assert snap["counters"]["resume_successes"] == 1


def test_aged_out_cursor_gets_stream_reset():
    hub = _hub(replay_capacity=3)
    first = hub.publish("build", "build.progress", {}, owner="p").id
    for _ in range(5):
        hub.publish("build", "build.progress", {}, owner="p")
    sub = hub.subscribe(["build"], principal="p", cursor=int(first))
    (frame,) = sub.drain()
    assert isinstance(frame, ControlEvent) and frame.type == "stream.reset"
    assert frame.payload["reason"] == "cursor_aged_out"
    assert frame.payload["head_id"] == hub.head_id
    assert hub.slo.snapshot()["counters"]["stream_resets"] == 1


def test_cursor_from_previous_epoch_resets():
    old = _hub(id_seed=5000)
    cursor = int(old.publish("build", "build.progress", {}, owner="p").id)
    new = _hub(id_seed=9000)
    new.publish("build", "build.progress", {}, owner="p")
    (frame, *_rest) = new.subscribe(["build"], principal="p", cursor=cursor).drain()
    assert frame.type == "stream.reset"
    ahead = _hub(id_seed=10).subscribe(["build"], principal="p", cursor=99)
    assert ahead.drain()[0].payload["reason"] == "cursor_ahead_of_stream"


def test_overflow_drops_oldest_and_signals_lagged():
    hub = _hub(subscriber_queue=3)
    sub = hub.subscribe(["build"], principal="p")
    published = [hub.publish("build", "build.log", {"i": i}, owner="p").id for i in range(6)]
    frames = sub.drain()
    assert isinstance(frames[0], ControlEvent) and frames[0].type == "stream.lagged"
    assert frames[0].payload == {"dropped": 3, "resume_from": "1000"}
    assert [f.id for f in frames[1:]] == published[-3:]
    snap = hub.slo.snapshot()
    assert snap["counters"]["events_dropped"] == 3
    assert snap["counters"]["stream_lagged"] == 3
    # The lagging client reconnects from its last delivered id (none yet) and
    # the ring replays everything, even beyond the live queue bound.
    resumed = hub.subscribe(["build"], principal="p", cursor=int(published[0]) - 1)
    assert [e.id for e in _events(resumed.drain())] == published


def test_secret_guard_redacts_keys_inline_credentials_and_token_shapes():
    hub = _hub()
    fake_pat = "gh" + "p_" + "A" * 36
    ev = hub.publish(
        "build",
        "build.log",
        {
            "line": f"cloning with {fake_pat}",
            "headers": {"Authorization": "Bearer abcdefghijklmnopqrstuvwxyz"},
            "nested": [{"api_key": "not-for-clients"}],
            "note": "password=hunter22",
            "ok": "compiled 12 files",
        },
        owner="p",
    )
    flat = ev.to_json()
    assert fake_pat not in flat
    assert "abcdefghijklmnopqrstuvwxyz" not in flat
    assert "not-for-clients" not in flat and "hunter22" not in flat
    assert ev.payload["ok"] == "compiled 12 files"
    assert hub.slo.snapshot()["counters"]["payload_redactions"] >= 4


def test_secret_guard_reject_mode_refuses_publish():
    hub = _hub(guard=PayloadSecretGuard(mode="reject"))
    with pytest.raises(RealtimeSecretError):
        hub.publish("agent", "agent.step", {"token": "abc123"}, owner="p")
    assert hub.head_id == "1000"
    assert hub.slo.snapshot()["counters"]["publish_rejected"] == 1


def test_authorizer_hook_denies_channels():
    hub = _hub(authorizer=lambda principal, channel: channel != "agent")
    with pytest.raises(RealtimeAuthError):
        hub.subscribe(["agent"], principal="p")
    assert hub.slo.snapshot()["counters"]["connect_failures"] == 1
    with pytest.raises(RealtimeAuthError):
        _hub().subscribe(["build"], principal="")


def test_presence_join_heartbeat_leave_snapshot_and_timeout():
    clock = {"ms": 1_792_252_800_000.0}
    hub = _hub(clock_ms=lambda: clock["ms"], presence_ttl_s=45)
    watcher = hub.subscribe(["presence"], principal="alice")
    first = watcher.drain()
    assert first[0].type == "presence.snapshot" and first[0].payload["count"] == 0
    hub.presence("join", client_id="tab-1", principal="alice", meta={"name": "Alice"})
    hub.presence("join", client_id="tab-2", principal="bob")
    clock["ms"] += 30_000
    hub.presence("heartbeat", client_id="tab-1", principal="alice")
    snap = hub.presence_snapshot()
    assert [m["client_id"] for m in snap["members"]] == ["tab-1", "tab-2"]
    with pytest.raises(RealtimeAuthError):
        hub.presence("join", client_id="tab-1", principal="mallory")
    hub.presence("leave", client_id="tab-1", principal="mallory")  # not the owner: no-op
    assert hub.presence_snapshot()["count"] == 2
    assert [m["client_id"] for m in hub.presence_snapshot(principal="alice")["members"]] == ["tab-1"]
    assert [m["client_id"] for m in hub.presence_snapshot(principal="bob")["members"]] == ["tab-2"]
    clock["ms"] += 20_000
    expired = hub.sweep_presence()
    assert [m.client_id for m in expired] == ["tab-2"]
    hub.presence("leave", client_id="tab-1", principal="alice")
    types = [(e.type, e.payload.get("client_id"), e.payload.get("reason")) for e in watcher.drain()]
    assert types == [
        ("presence.joined", "tab-1", None),
        ("presence.left", "tab-1", "left"),
    ]
    assert hub.presence_snapshot()["count"] == 0
    assert hub.slo.snapshot()["counters"]["presence_timeouts"] == 1


def test_publish_is_thread_safe_and_wakes_async_consumer():
    hub = _hub()

    async def scenario():
        sub = hub.subscribe(["build"], principal="p")

        def worker():
            for i in range(50):
                hub.publish("build", "build.progress", {"i": i}, owner="p")

        t = threading.Thread(target=worker)
        t.start()
        got = []
        while len(got) < 50:
            frame = await sub.next(timeout=2.0)
            assert frame is not None
            got.append(frame)
        t.join()
        return got

    got = asyncio.run(scenario())
    assert [int(e.id) for e in got] == list(range(1001, 1051))


def test_slo_bridges_into_existing_metrics_collector():
    metrics = MetricsCollector()
    hub = _hub()
    hub.slo.bind_sink(metrics)
    hub.subscribe(["build"], principal="p")
    hub.publish("build", "build.started", {}, owner="p")
    hub.slo.record_delivered("build", 12.5)
    snap = metrics.snapshot()
    assert any(k.startswith("realtime.events_published") for k in snap["counters"])
    assert any(k.startswith("realtime.connect_successes") for k in snap["counters"])
    assert any(k.startswith("realtime.delivery_latency_ms") for k in snap["histograms"])
    slo = hub.slo.snapshot()
    assert slo["targets"]["delivery_latency_p95_ms_max"] == 500.0
    assert slo["targets"]["delivery_latency_p99_ms_max"] == 2000.0
    assert slo["slo_met"]["connect_success_rate"] is True


def test_job_sink_resequences_and_keeps_producer_id():
    hub = _hub()
    sink = HubJobEventSink(hub)
    assert isinstance(sink, JobEventPublisher)
    assert isinstance(NullJobEventPublisher(), JobEventPublisher)
    producer = [
        {"v": 1, "id": 1, "ts": 1.0, "channel": "build", "type": "build.started", "payload": {}, "job_id": "job-9", "correlation_id": "req-1"},
        {"v": 1, "id": 1, "ts": 1.0, "channel": "agent", "type": "agent.started", "payload": {"a": 1}, "correlation_id": ""},
        {"v": 1, "id": 2, "ts": 1.0, "channel": "build", "type": "build.completed", "payload": {"secret": "x"}, "job_id": "job-9"},
    ]
    out = [sink.publish(e) for e in producer]
    assert [e.id for e in out] == ["1001", "1002", "1003"]
    assert [e.payload["source_id"] for e in out] == ["1", "1", "2"]
    assert out[0].job_id == "job-9" and out[0].correlation_id == "req-1"
    assert out[1].correlation_id is None
    assert out[2].payload["secret"] == "[REDACTED]"
    assert sink.publish({"type": "presence.joined", "payload": {}}) is None
    assert sink.publish({"type": "nonsense"}) is None
    assert sink.rejected == 2 and sink.accepted == 3


def test_attach_hub_subscribes_to_fanout_shaped_publisher():
    class FanOut:
        def __init__(self):
            self.subs = []

        def subscribe(self, sink):
            self.subs.append(sink)
            return lambda: self.subs.remove(sink)

        def publish(self, event):
            for s in list(self.subs):
                s.publish(dict(event))

    hub = _hub()
    fan = FanOut()
    unsubscribe = attach_hub(fan, HubJobEventSink(hub))
    fan.publish({"id": 7, "type": "agent.step", "payload": {}, "job_id": "j"})
    assert hub.head_id == "1001"
    unsubscribe()
    assert fan.subs == []
    assert attach_hub(None, HubJobEventSink(hub)) is None
    assert attach_hub(NullJobEventPublisher(), HubJobEventSink(hub)) is None


def test_aclose_ends_consumers():
    async def scenario():
        hub = _hub()
        sub = hub.subscribe(["build"], principal="p")
        hub.start()
        await hub.aclose()
        with pytest.raises(EOFError):
            await sub.next(timeout=1)
        with pytest.raises(RuntimeError):
            hub.publish("build", "build.log", {}, owner="p")

    asyncio.run(scenario())
