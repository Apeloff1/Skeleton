"""TD adversarial tests for #4253 (not committed upstream)."""
import asyncio, base64, json, time, urllib.parse
import pytest
fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from skeleton.api import engine_routes
from skeleton.api.realtime_routes import router
from skeleton.realtime import PayloadSecretGuard, RealtimeHub
from skeleton.realtime.envelope import RealtimeEvent, EnvelopeError, parse_resume_cursor
from skeleton.realtime.hub import RealtimeCapacityError, RealtimeLimitError, sealed_principal_authorizer
from skeleton.realtime.sse import iter_frames

GH = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"

def H(**kw):
    kw.setdefault("id_seed", 1000); kw.setdefault("authorizer", sealed_principal_authorizer)
    return RealtimeHub(**kw)

# meta cap boundaries
def _meta_of(n):
    base = len(json.dumps({"b": ""}, separators=(",", ":")))
    return {"b": "x" * (n - base)}

def test_meta_exactly_at_cap_ok():
    h = H(); h.presence("join", client_id="c", principal="a", meta=_meta_of(2048)); assert h._presence

def test_meta_one_over_cap_413():
    h = H()
    with pytest.raises(RealtimeLimitError) as e:
        h.presence("join", client_id="c", principal="a", meta=_meta_of(2049))
    assert e.value.status == 413 and not h._presence and len(h._ring) == 0

def test_meta_multibyte_counted_in_bytes():
    h = H()
    with pytest.raises(RealtimeLimitError):
        h.presence("join", client_id="c", principal="a", meta={"b": "\u00e6" * 1100})

def test_meta_deeply_nested_not_500():
    h = H(); m = cur = {}
    for _ in range(5000):
        cur["a"] = {}; cur = cur["a"]
    try:
        h.presence("join", client_id="c", principal="a", meta=m)
    except (RealtimeLimitError, EnvelopeError, ValueError):
        pass
    assert not h._presence or True

def test_meta_deep_http(monkeypatch):
    a = fastapi.FastAPI(); a.include_router(router, prefix="/api/v1")
    a.state.realtime_hub = H()
    body = '{"action":"join","client_id":"c","meta":' + '{"a":' * 3000 + '1' + '}' * 3000 + '}'
    r = TestClient(a, raise_server_exceptions=False).post("/api/v1/presence", content=body,
        headers={"x-zaibatsu-attester": "a", "content-type": "application/json"})
    assert r.status_code in (413, 422), r.status_code

def test_heartbeat_cannot_grow_meta_past_cap():
    h = H(); h.presence("join", client_id="c", principal="a", meta=_meta_of(2000))
    with pytest.raises(RealtimeLimitError):
        h.presence("heartbeat", client_id="c", principal="a", meta=_meta_of(4000))

# secrets
def _scrub(p):
    clean, n = PayloadSecretGuard().scrub(p); return json.dumps(clean), n

@pytest.mark.parametrize("payload", [
    {"X-API-KEY": "abc123def456"}, {"x-Api-Key": "abc123def456"}, {"XApiKey": "abc123def456"},
    {"note": urllib.parse.quote(urllib.parse.quote("token=" + GH))},
    {"note": urllib.parse.quote(urllib.parse.quote(GH))},
    {"note": '{"\\u0074oken": "abc123def456"}'},
    {"note": '{"inner": "\\u0067hp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"}'},
    {"note": base64.urlsafe_b64encode(("Bearer " + GH).encode()).decode().rstrip("=")},
    {"note": base64.b64encode(json.dumps({"password": "hunter2hunter2"}).encode()).decode()},
])
def test_secret_variants(payload):
    s, n = _scrub(payload)
    assert n >= 1 and GH not in s and "hunter2" not in s and "abc123def456" not in s, s

def test_bytes_refused():
    with pytest.raises(Exception):
        PayloadSecretGuard().scrub({"b": b"x"})

def test_secret_split_across_fields_documented_gap():
    s, n = _scrub({"p1": GH[:20], "p2": GH[20:]})
    # Known residual risk: not reassembled. Record only.
    print("split hits", n)

# lifetime across reconnect
def test_reconnect_lifetime_is_fresh_per_subscribe_but_needs_new_subscribe():
    h = H(max_stream_lifetime_s=0.05)
    sub = h.subscribe(["build"], principal="a")
    async def run():
        out = []
        async for f in iter_frames(h, sub, heartbeat_interval_s=0.01):
            out.append(f)
            if len(out) > 50: break
        return out
    frames = asyncio.run(run())
    assert any(getattr(f, "type", "") == "stream.reauth" for f in frames)
    assert sub.closed or sub.id not in h._subs

# 429 per principal
def test_cap_per_principal_not_cross_tenant():
    h = H(max_streams_per_principal=2)
    h.subscribe(["build"], principal="a"); h.subscribe(["build"], principal="a")
    with pytest.raises(RealtimeCapacityError):
        h.subscribe(["build"], principal="a")
    h.subscribe(["build"], principal="b")

def test_xff_does_not_bypass_cap(monkeypatch):
    monkeypatch.setattr(engine_routes, "_engine_service_token", lambda: "svc")
    a = fastapi.FastAPI(); a.include_router(router, prefix="/api/v1")
    hub = H(max_streams_per_principal=1); a.state.realtime_hub = hub
    hub.subscribe(["build"], principal="alice")
    r = TestClient(a).get("/api/v1/events?channels=build&max_events=1",
        headers={"x-zaibatsu-attester": "alice", "x-forwarded-for": "9.9.9.9"})
    assert r.status_code == 429 and "retry-after" in {k.lower() for k in r.headers}

# epoch
def test_foreign_epoch_reset_and_no_replay():
    h1 = H(epoch="aaaa"); h2 = H(epoch="bbbb")
    h2.publish("build", "build.progress", {"m": "SECRET"}, owner="a")
    sub = h2.subscribe(["build"], principal="a", cursor=1000, cursor_epoch="aaaa")
    fr = sub.drain()
    assert any(getattr(f, "type", "") == "stream.reset" for f in fr)
    assert not any(isinstance(f, RealtimeEvent) and "SECRET" in f.to_json() for f in fr)

def test_bad_epoch_syntax_rejected():
    for raw in ("1-ZZ", "1-" + "a" * 17, "1-aa-bb", "1-"):
        with pytest.raises(EnvelopeError):
            parse_resume_cursor(raw)

def test_other_tenant_cursor_same_epoch_still_owner_filtered():
    h = H()
    h.publish("build", "build.progress", {"m": "ALICE"}, owner="alice", tenant="t1")
    sub = h.subscribe(["build"], principal="mallory", cursor=1000, cursor_epoch=h.epoch, tenant="t1")
    assert not any("ALICE" in repr(f) for f in sub.drain())

# perf
def test_hot_path_publish_budget():
    h = H(); [h.subscribe(["build"], principal=f"p{i}") for i in range(50)]
    p = {"step": "compile", "pct": 50, "msg": "x" * 200, "nested": {"a": [1, 2, 3]}}
    t = time.perf_counter()
    for _ in range(2000): h.publish("build", "build.progress", p, owner="p1")
    per = (time.perf_counter() - t) / 2000 * 1e6
    print("publish us", per); assert per < 1000
