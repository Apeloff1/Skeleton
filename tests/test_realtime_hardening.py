"""Jenkins #4128 Sev2 hardening + #4139 re-check acceptance tests."""

from __future__ import annotations

import asyncio
import base64
import json

import pytest

from skeleton.realtime import PayloadSecretGuard, RealtimeHub, RealtimeSecretError
from skeleton.realtime.envelope import (
    ControlEvent,
    EnvelopeError,
    RealtimeEvent,
    parse_resume_cursor,
)
from skeleton.realtime.guard import is_sensitive_key
from skeleton.realtime.hub import (
    RealtimeCapacityError,
    RealtimeLimitError,
    sealed_principal_authorizer,
)
from skeleton.realtime.sse import SSEParser, iter_frames, sse_body, sse_message_to_frame

REDACTED_MARK = "REDACTED"


def _hub(**kw):
    kw.setdefault("id_seed", 1000)
    kw.setdefault("authorizer", sealed_principal_authorizer)
    return RealtimeHub(**kw)


def _events(frames):
    return [
        f
        for f in frames
        if isinstance(f, RealtimeEvent) and f.type != "presence.snapshot"
    ]


# -- S2-1 presence bounds ------------------------------------------------------
def test_presence_2mb_meta_rejected_before_anything_is_stored():
    hub = _hub()
    published = hub.head_seq
    giant = {"blob": "x" * (2 * 1024 * 1024)}
    with pytest.raises(RealtimeLimitError) as exc:
        hub.presence("join", client_id="c1", principal="alice", meta=giant)
    assert exc.value.status == 413
    assert hub._presence == {} and hub.head_seq == published and len(hub._ring) == 0


def test_giant_meta_cannot_break_later_presence_subscriptions():
    hub = _hub()
    with pytest.raises(RealtimeLimitError):
        hub.presence(
            "join",
            client_id="c1",
            principal="alice",
            meta={"blob": "x" * (2 * 1024 * 1024)},
        )
    hub.presence("join", client_id="c2", principal="alice", meta={"ok": 1})
    sub = hub.subscribe(["presence"], principal="alice")
    snap = [
        f
        for f in sub.drain()
        if isinstance(f, RealtimeEvent) and f.type == "presence.snapshot"
    ]
    assert snap and [m["client_id"] for m in snap[0].payload["members"]] == ["c2"]


def test_presence_members_per_scope_capped():
    hub = _hub(presence_max_members_per_scope=2)
    hub.presence("join", client_id="a", principal="p")
    hub.presence("join", client_id="b", principal="p")
    with pytest.raises(RealtimeLimitError) as exc:
        hub.presence("join", client_id="c", principal="p")
    assert exc.value.status == 422 and len(hub._presence) == 2
    hub.presence("join", client_id="c", principal="p", scope="other")


# -- S2-2 presence scope -------------------------------------------------------
def test_presence_scope_visibility_follows_scope_authorizer():
    allowed = {("bob", "room-1")}
    hub = _hub(presence_scope_authorizer=lambda p, s: (p, s) in allowed)
    bob = hub.subscribe(["presence"], principal="bob")
    mallory = hub.subscribe(["presence"], principal="mallory")
    hub.presence("join", client_id="alice-1", principal="alice", scope="room-1")
    assert [e.type for e in _events(bob.drain())] == ["presence.joined"]
    assert _events(mallory.drain()) == []
    assert [
        m["client_id"]
        for m in hub.presence_snapshot("room-1", principal="bob")["members"]
    ] == ["alice-1"]
    assert hub.presence_snapshot("room-1", principal="mallory")["members"] == []
    late = hub.subscribe(["presence"], principal="bob", cursor=1000)
    frames = late.drain()
    assert any(
        isinstance(f, RealtimeEvent) and f.type == "presence.joined" for f in frames
    )


# -- S2-3 secret guard ---------------------------------------------------------
@pytest.mark.parametrize(
    "key",
    [
        "x-api-key",
        "X-Api-Key",
        "accessToken",
        "aws_secret_access_key",
        "sessionId",
        "dbCredential",
    ],
)
def test_guard_normalizes_and_matches_key_tokens(key):
    assert is_sensitive_key(key)
    clean, hits = PayloadSecretGuard().scrub({key: "value-123"})
    assert hits == 1 and clean[key] != "value-123"


def test_guard_scans_json_embedded_in_string():
    clean, hits = PayloadSecretGuard().scrub(
        {"note": json.dumps({"password": "hunter2", "ok": 1})}
    )
    assert hits >= 1 and "hunter2" not in json.dumps(clean)


def test_guard_decodes_percent_encoded_values():
    clean, hits = PayloadSecretGuard().scrub({"q": "token%3Dghp_" + "a" * 36})
    assert hits >= 1 and "ghp_" not in json.dumps(clean)


def test_guard_decodes_base64_values():
    raw = base64.b64encode(("password=" + "s3cr3tvalue").encode()).decode()
    clean, hits = PayloadSecretGuard().scrub({"blob": raw})
    assert hits >= 1 and clean["blob"] != raw


@pytest.mark.parametrize("value", [b"token=abc", bytearray(b"x"), {1, 2}, object()])
def test_guard_rejects_bytes_and_non_json_values(value):
    with pytest.raises(RealtimeSecretError):
        PayloadSecretGuard().scrub({"v": value})


def test_guard_scans_non_string_scalars_by_str():
    clean, hits = PayloadSecretGuard().scrub({"n": 42, "f": 1.5, "b": True, "z": None})
    assert hits == 0 and clean == {"n": 42, "f": 1.5, "b": True, "z": None}


def test_envelope_refuses_non_json_native_payload():
    with pytest.raises(EnvelopeError):
        RealtimeEvent(
            id="1",
            ts="2026-10-24T16:00:00.000Z",
            channel="build",
            type="build.log",
            payload={"x": object()},
        )


# -- S2-4 stream lifetime ------------------------------------------------------
def test_stream_lifetime_emits_reauth_then_closes():
    async def run():
        hub = _hub(max_stream_lifetime_s=0.05)
        sub = hub.subscribe(["build"], principal="p")
        hub.publish("build", "build.log", {"n": 1}, owner="p")
        frames = [f async for f in iter_frames(hub, sub, heartbeat_interval_s=1.0)]
        return hub, frames

    hub, frames = asyncio.run(run())
    assert isinstance(frames[-1], ControlEvent) and frames[-1].type == "stream.reauth"
    assert frames[-1].payload["cursor"] == hub.cursor_for("1001")
    assert hub._subs == {}


def test_sdk_client_reconnects_immediately_on_reauth():
    from skeleton.client.realtime import RealtimeClient
    from skeleton.client.realtime.transport import InProcessTransport

    async def run():
        hub = _hub(max_stream_lifetime_s=0.05)
        sleeps = []

        async def sleep(d):
            sleeps.append(d)

        client = RealtimeClient(
            InProcessTransport(hub, principal="p"), channels=("build",), sleep=sleep
        )
        hub.publish("build", "build.log", {"n": 1}, owner="p")
        seen = []
        async for frame in client.frames():
            seen.append(frame)
            if (
                sum(
                    1
                    for f in seen
                    if isinstance(f, ControlEvent) and f.type == "stream.reauth"
                )
                >= 2
            ):
                client.close()
        return client, sleeps

    client, sleeps = asyncio.run(asyncio.wait_for(run(), 5))
    assert client.stats["reauths"] >= 2 and client.stats["reconnects"] >= 1
    assert sleeps == [] and client.backoff.attempt == 0


# -- S2-5 per-principal cap ----------------------------------------------------
def test_per_principal_stream_cap():
    hub = _hub(max_streams_per_principal=2)
    hub.subscribe(["build"], principal="p")
    hub.subscribe(["build"], principal="p")
    with pytest.raises(RealtimeCapacityError):
        hub.subscribe(["build"], principal="p")
    hub.subscribe(["build"], principal="q")


def test_per_client_cap_returns_429_with_retry_after():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from skeleton.api.realtime_routes import router

    app = fastapi.FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.realtime_hub = _hub(max_streams_per_principal=1)
    app.state.realtime_hub.subscribe(["build"], principal="alice")
    r = TestClient(app).get(
        "/api/v1/events?channels=build&max_events=1",
        headers={"x-zaibatsu-attester": "alice"},
    )
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert r.json()["detail"]["error"] == "too_many_streams"


# -- S2-6 cursors --------------------------------------------------------------
def test_foreign_epoch_cursor_gets_stream_reset():
    hub = _hub(epoch="aaaa0001")
    hub.publish("build", "build.log", {"n": 1}, owner="p")
    sub = hub.subscribe(["build"], principal="p", cursor=1000, cursor_epoch="bbbb0002")
    (frame,) = sub.drain()
    assert (
        frame.type == "stream.reset"
        and frame.payload["reason"] == "cursor_foreign_instance"
    )
    own = hub.subscribe(["build"], principal="p", cursor=1000, cursor_epoch="aaaa0001")
    assert [e.payload for e in _events(own.drain())] == [{"n": 1}]


def test_legacy_cursor_below_hub_seed_gets_reset():
    hub = _hub()
    sub = hub.subscribe(["build"], principal="p", cursor=5)
    assert sub.drain()[0].type == "stream.reset"


def test_sse_id_line_carries_epoch_and_round_trips():
    async def run():
        hub = _hub(epoch="abc123")
        sub = hub.subscribe(["build"], principal="p")
        hub.publish("build", "build.log", {"n": 1}, owner="p")
        return "".join([c async for c in sse_body(hub, sub, max_events=1)])

    text = asyncio.run(run())
    assert "id: 1001-abc123\n" in text
    (msg,) = list(SSEParser().feed(text))
    assert sse_message_to_frame(msg).id == "1001"
    assert parse_resume_cursor("1001-abc123") == (1001, "abc123")
    with pytest.raises(EnvelopeError):
        parse_resume_cursor("1001-NOT_HEX")


# -- verified-tenant subscriptions --------------------------------------------
def test_verified_tenant_subscription_gets_own_tenant_events_live_and_replay():
    hub = _hub()
    hub.publish("build", "build.progress", {"n": 1}, owner="alice", tenant="t1")
    hub.publish("build", "build.progress", {"n": 2}, owner="alice", tenant="t2")
    hub.publish("build", "build.progress", {"n": 3}, owner="bob", tenant="t1")
    sub = hub.subscribe(["build"], principal="alice", tenant="t1", cursor=1000)
    hub.publish("build", "build.progress", {"n": 4}, owner="alice", tenant="t1")
    assert [e.payload["n"] for e in _events(sub.drain())] == [1, 4]
    plain = hub.subscribe(["build"], principal="alice", cursor=1000)
    assert _events(plain.drain()) == []
    other_tenant = hub.subscribe(["build"], principal="alice", tenant="t3", cursor=1000)
    assert _events(other_tenant.drain()) == []
    bob = hub.subscribe(["build"], principal="carol", tenant="t1", cursor=1000)
    assert _events(bob.drain()) == []


_FAKE_GH = "ghp_" + "A" * 36


@pytest.mark.parametrize(
    "value",
    [
        f"token%253D{_FAKE_GH}",  # double-%-encoded '='
        f"token%25253D{_FAKE_GH}",  # triple-%-encoded '='
        f"note%2520{_FAKE_GH}",  # double-%-encoded space
    ],
)
def test_guard_catches_multi_percent_encoded_tokens(value):
    clean, hits = PayloadSecretGuard().scrub({"note": value})
    assert hits and _FAKE_GH not in json.dumps(clean)


@pytest.mark.parametrize(
    "value",
    [
        f"x{_FAKE_GH}",
        f"tokenghp_{'B' * 36}",
        f"zAKIA{'D' * 16}",
    ],
)
def test_guard_catches_tokens_glued_to_leading_alphanumeric(value):
    clean, hits = PayloadSecretGuard().scrub({"note": value})
    assert hits and clean["note"] != value


def test_guard_reject_mode_refuses_glued_and_double_encoded_tokens():
    guard = PayloadSecretGuard(mode="reject")
    for value in (f"x{_FAKE_GH}", f"token%253D{_FAKE_GH}"):
        with pytest.raises(RealtimeSecretError):
            guard.scrub({"note": value})


def test_guard_percent_decoding_is_bounded():
    from skeleton.realtime.guard import _MAX_DECODE_ROUNDS, _decoded_variants

    deep = "%25" * 10 + "41"
    assert len(_decoded_variants(deep)) <= _MAX_DECODE_ROUNDS


def test_realtime_limits_from_env(monkeypatch):
    from skeleton.realtime import realtime_limits_from_env

    monkeypatch.setenv("SKELETON_REALTIME_MAX_STREAMS_PER_PRINCIPAL", "3")
    monkeypatch.setenv("SKELETON_REALTIME_PRESENCE_MAX_MEMBERS", "-1")
    limits = realtime_limits_from_env()
    assert limits["max_streams_per_principal"] == 3
    assert limits["presence_max_members_per_scope"] == 256


def _b64(text):
    return base64.b64encode(text.encode()).decode()


def test_guard_redacts_values_still_decoding_past_the_bound():
    from urllib.parse import quote

    deep = "a b"
    for _ in range(6):  # six %-layers: still decoding after the 3-layer bound
        deep = quote(deep, safe="")
    clean, hits = PayloadSecretGuard().scrub({"note": deep})
    assert hits and clean["note"] != deep
    with pytest.raises(RealtimeSecretError):
        PayloadSecretGuard(mode="reject").scrub({"note": deep})


@pytest.mark.parametrize(
    "value",
    [
        _b64(f"token%3D{_FAKE_GH}"),  # base64(%-enc)
        _b64(f"x {_FAKE_GH}").replace("=", "%3D"),  # %-enc(base64)
        _b64(_b64(f"note {_FAKE_GH}")),  # double base64
        _b64(_b64("password=s3cr3tvalue")),  # double base64, key=value
    ],
)
def test_guard_catches_interleaved_percent_and_base64_layers(value):
    clean, hits = PayloadSecretGuard().scrub({"blob": value})
    assert hits and clean["blob"] != value
    with pytest.raises(RealtimeSecretError):
        PayloadSecretGuard(mode="reject").scrub({"blob": value})


@pytest.mark.parametrize(
    "value",
    [
        "ask-a-question-about-the-build-pipeline",
        "risk-assessment-for-the-quarterly-release",
        "task-" + "a" * 30,
    ],
)
def test_guard_keeps_prose_containing_sk_dash(value):
    clean, hits = PayloadSecretGuard().scrub({"note": value})
    assert hits == 0 and clean["note"] == value


def test_guard_still_catches_standalone_sk_key():
    value = "key sk-" + "c" * 24
    clean, hits = PayloadSecretGuard().scrub({"note": value})
    assert hits and "sk-" + "c" * 24 not in clean["note"]
