"""Seal v3: request binding + replay/skew protection (Jenkins #4594 follow-up).

The MAC covers method, canonical path + query, sha256(body), tenant, domain and
issue timestamp; nonces are single-use; timestamps outside the skew window fail.
"""

from __future__ import annotations

import time

import httpx
import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from skeleton.api import hmac_seal as hs
from skeleton.api.middleware import AuthError, GatePolicy, RequestSealMiddleware
from skeleton.api.nonce_store import (
    InMemoryNonceStore,
    NonceStore,
    NonceStoreFull,
    max_entries_from_env,
)
from skeleton.client import seal as cs
from skeleton.client.gateway import GatewayClient

SECRET = "seal-v3-test-secret"
NOW = 1_700_000_000
REQ = dict(method="POST", path="/api/v1/projects/p1", query="b=2&a=1", body=b'{"x":1}', tenant="t1")


def _store():
    return InMemoryNonceStore(clock=lambda: NOW)


def _sreq(method="POST", path="/api/v1/projects/p1", query="b=2&a=1", body=b'{"x":1}', tenant="t1"):
    return hs.SealRequest(method, path, query, body, tenant)


def _mint(**kw):
    args = {**REQ, "secret": SECRET, "now": NOW}
    args.update(kw)
    return hs.mint_seal_v3("svc", "projects", **args)


def _v(tok, req=None, cache=None, now=NOW, **kw):
    return hs.verify_seal(
        tok, secret=SECRET, keyring="", now=now, domain="projects", enforce_domain=True,
        nonce_store=cache if cache is not None else _store(),
        request=req if req is not None else _sreq(), **kw,
    )


def test_v3_roundtrip_and_wire_shape():
    tok = _mint(principal="u1")
    parts = tok.split(".")
    assert parts[0] == "v3" and len(parts) == 8
    assert parts[1:6] == ["u1", "svc", "projects", "t1", str(NOW)]
    assert _v(tok) == "svc"


@pytest.mark.parametrize(
    "field,value",
    [
        ("method", "PUT"),
        ("path", "/api/v1/projects/p2"),
        ("query", "a=1&b=3"),
        ("query", "a=1"),
        ("body", b'{"x":2}'),
        ("body", b""),
        ("tenant", "t2"),
        ("tenant", None),
    ],
)
def test_each_bound_field_tamper_rejected(field, value):
    tok = _mint()
    with pytest.raises(AuthError):
        _v(tok, req=_sreq(**{field: value}))


def test_query_order_and_encoding_canonical():
    tok = _mint(query="a=1&b=2", path="/api/v1/projects/p%201")
    assert _v(tok, req=_sreq(query="b=2&a=1", path="/api/v1/projects/p 1")) == "svc"
    assert hs.canonical_query("b=2&a=1&a=0") == "a=0&a=1&b=2"
    assert hs.canonical_path("/x/%7Euser") == "/x/~user"


def test_tampered_wire_tenant_or_ts_rejected():
    tok = _mint()
    p = tok.split(".")
    for idx, new in ((4, "t2"), (5, str(NOW + 1))):
        q = list(p)
        q[idx] = new
        with pytest.raises(AuthError):
            _v(".".join(q), req=_sreq(tenant=q[4] if idx == 4 else "t1"))


def test_replayed_nonce_rejected_within_window():
    cache = _store()
    tok = _mint()
    assert _v(tok, cache=cache) == "svc"
    with pytest.raises(AuthError):
        _v(tok, cache=cache, now=NOW + 10)


def test_skew_window_both_directions():
    assert _v(_mint(now=NOW - hs.SEAL_SKEW_SECS)) == "svc"
    assert _v(_mint(now=NOW + hs.SEAL_SKEW_SECS)) == "svc"
    for off in (-hs.SEAL_SKEW_SECS - 1, hs.SEAL_SKEW_SECS + 1):
        with pytest.raises(AuthError):
            _v(_mint(now=NOW + off))
    with pytest.raises(AuthError):
        _v(_mint(now=NOW - 20), skew_secs=10)


def test_replay_entry_outlives_skew_window():
    cache = _store()
    tok = _mint(now=NOW)
    _v(tok, cache=cache)
    # Still inside the window at the edge → still a replay.
    with pytest.raises(AuthError):
        _v(tok, cache=cache, now=NOW + hs.SEAL_SKEW_SECS)


def test_v3_without_request_rejected_and_no_fallback():
    tok = _mint()
    with pytest.raises(AuthError):
        hs.verify_seal(tok, secret=SECRET, keyring="", now=NOW, domain="projects", enforce_domain=True)
    with pytest.raises(AuthError):
        _v(tok[:-1] + ("0" if tok[-1] != "0" else "1"))


def test_v3_valid_signature_without_atomic_nonce_store_fails_closed():
    # Direct verification cannot silently turn a single-use seal into a reusable bearer.
    with pytest.raises(AuthError):
        hs.verify_seal(
            _mint(), secret=SECRET, keyring="", now=NOW, domain="projects",
            enforce_domain=True, request=_sreq(), nonce_store=None,
        )


def test_cross_domain_and_unchartered_rejected():
    tok = _mint()
    with pytest.raises(AuthError):
        hs.verify_seal(tok, secret=SECRET, keyring="", now=NOW, domain="realtime",
                       enforce_domain=True, request=_sreq(), nonce_store=_store())
    with pytest.raises(AuthError):
        hs.verify_seal(tok, secret=SECRET, keyring="", now=NOW, domain=None,
                       enforce_domain=True, request=_sreq(), nonce_store=_store())


def test_keyring_rotation_v3():
    tok = hs.mint_seal_v3("svc", "projects", secret="old", now=NOW, **REQ)
    assert hs.verify_seal(tok, secret="new", keyring="k1=old", now=NOW, domain="projects",
                          enforce_domain=True, request=_sreq(),
                          nonce_store=_store()) == "svc"


def test_uses_constant_time_compare(monkeypatch):
    calls = []
    real = hs.hmac.compare_digest
    monkeypatch.setattr(hs.hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    _v(_mint())
    assert len(calls) >= 3  # MAC, tenant, domain


def test_client_server_byte_parity():
    kw = dict(REQ, secret=SECRET, now=NOW, nonce="n" * 32, principal="u1")
    assert cs.mint_request_seal_token("svc", "projects", **kw) == hs.mint_seal_v3("svc", "projects", **kw)
    assert cs.canonical_query("z=&a=%20b") == hs.canonical_query("z=&a=%20b")
    assert cs.canonical_path("/a b/%41") == hs.canonical_path("/a b/%41")


def test_mint_validation():
    with pytest.raises(ValueError):
        _mint(tenant="bad.tenant")
    with pytest.raises(ValueError):
        _mint(nonce="short")
    with pytest.raises(ValueError):
        cs.mint_request_seal_token("svc", "projects", method="P OST", path="/", secret=SECRET)


def test_sealer_bind_requires_domain():
    with pytest.raises(cs.SkeletonSealConfigError):
        cs.RequestSealer("svc", seal_secret=SECRET, bind_request=True)


# --- middleware + dependency ------------------------------------------------------


@pytest.fixture()
def gated(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    monkeypatch.delenv("GF_SEAL_KEYRING", raising=False)
    monkeypatch.delenv("GF_SEAL_LEGACY", raising=False)
    app = FastAPI()

    @app.post("/api/v1/projects/{pid}")
    async def write(pid: str, request: Request, who: str = Depends(hs.require_seal)):
        return {"pid": pid, "body": (await request.body()).decode(), "who": who,
                "tenant": request.state.seal_tenant}

    app.add_middleware(RequestSealMiddleware, policy=GatePolicy())
    return TestClient(app)


def _live(**kw):
    args = dict(REQ, secret=SECRET)
    args.update(kw)
    return hs.mint_seal_v3("svc", "projects", **args)


def test_middleware_v3_ok_body_replayed_then_replay_401(gated):
    h = {"x-gf-seal": _live(), "x-gf-tenant": "t1", "content-type": "application/json"}
    r = gated.post("/api/v1/projects/p1?b=2&a=1", content=b'{"x":1}', headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"pid": "p1", "body": '{"x":1}', "who": "svc", "tenant": "t1"}
    r = gated.post("/api/v1/projects/p1?b=2&a=1", content=b'{"x":1}', headers=h)
    assert r.status_code == 401 and r.json() == {"error": "invalid_seal"}


@pytest.mark.parametrize(
    "url,body,tenant",
    [
        ("/api/v1/projects/p1?b=2&a=1", b'{"x":2}', "t1"),
        ("/api/v1/projects/p2?b=2&a=1", b'{"x":1}', "t1"),
        ("/api/v1/projects/p1?a=1", b'{"x":1}', "t1"),
        ("/api/v1/projects/p1?b=2&a=1", b'{"x":1}', "t2"),
        ("/api/v1/projects/p1?b=2&a=1", b'{"x":1}', None),
    ],
)
def test_middleware_rejects_altered_request(gated, url, body, tenant):
    h = {"x-gf-seal": _live()}
    if tenant:
        h["x-gf-tenant"] = tenant
    assert gated.post(url, content=body, headers=h).status_code == 401


def test_middleware_stale_timestamp_401(gated):
    h = {"x-gf-seal": _live(now=time.time() - hs.SEAL_SKEW_SECS - 5), "x-gf-tenant": "t1"}
    assert gated.post("/api/v1/projects/p1?b=2&a=1", content=b'{"x":1}', headers=h).status_code == 401


def test_middleware_duplicate_tenant_header_401(gated):
    tok = _live()
    r = gated.post("/api/v1/projects/p1?b=2&a=1", content=b'{"x":1}',
                   headers=[("x-gf-seal", tok), ("x-gf-tenant", "t1"), ("x-gf-tenant", "t2")])
    assert r.status_code == 401


def test_middleware_oversized_body_401(gated, monkeypatch):
    monkeypatch.setattr(hs, "MAX_SEALED_BODY_BYTES", 4)
    tok = _live()
    r = gated.post("/api/v1/projects/p1?b=2&a=1", content=b'{"x":1}',
                   headers={"x-gf-seal": tok, "x-gf-tenant": "t1"})
    assert r.status_code == 401


def test_require_seal_rejects_v3_not_verified_by_middleware(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    app = FastAPI()

    @app.post("/w")
    def w(who: str = Depends(hs.require_seal)):
        return {"who": who}

    r = TestClient(app, raise_server_exceptions=False).post("/w", headers={"x-gf-seal": _live()})
    assert r.status_code != 200


def test_gateway_client_v3_end_to_end(gated):
    client = GatewayClient(
        base_url="http://testserver", client=gated, seal_attester="svc", seal_secret=SECRET,
        seal_domain="projects", seal_bind_request=True, seal_tenant="t1",
    )
    for _ in range(2):  # fresh nonce per request
        r = client._request("POST", "/api/v1/projects/p9", json={"k": "v"}, params={"z": "1", "a": "2"})
        assert r.status_code == 200, r.text
        assert r.json()["pid"] == "p9" and r.json()["tenant"] == "t1"
    assert isinstance(gated, httpx.Client)


# --- NonceStore port ---------------------------------------------------------------


def test_nonce_store_fresh_replay_scope_ttl():
    t = [1000.0]
    st = InMemoryNonceStore(clock=lambda: t[0])
    assert st.check_and_record("seal", "n1", 1000.0, 10) is True
    assert st.check_and_record("seal", "n1", 1000.0, 10) is False
    assert st.check_and_record("s2s:svc", "n1", 1000.0, 10) is True  # scopes are separate
    t[0] = 1011.0
    assert st.check_and_record("seal", "n1", 1011.0, 10) is True  # expired → fresh again
    assert st.check_and_record("seal", "", 1011.0, 10) is False
    assert st.check_and_record("seal", "x", 1011.0, 0) is False


def test_full_store_never_evicts_live_nonce_replay_still_rejected():
    # (a) LRU would have evicted "a" to admit "c"; fail-closed refuses "c" instead.
    t = [0.0]
    st = InMemoryNonceStore(max_entries=2, clock=lambda: t[0])
    assert st.check_and_record("seal", "a", 0, 100)
    assert st.check_and_record("seal", "b", 0, 100)
    with pytest.raises(NonceStoreFull) as ei:
        st.check_and_record("seal", "c", 0, 100)
    assert ei.value.retry_after_s == 100
    assert st.check_and_record("seal", "a", 0, 100) is False  # replay of live nonce
    assert st.check_and_record("seal", "b", 0, 100) is False
    assert st.stats()["nonce_store_full"] == 1 and st.nonce_store_full == 1
    with pytest.raises(ValueError):
        InMemoryNonceStore(max_entries=0)


def test_full_store_reclaims_expired_under_pressure():
    # (b) expired entries are reclaimed before refusing.
    t = [0.0]
    st = InMemoryNonceStore(max_entries=2, clock=lambda: t[0])
    assert st.check_and_record("seal", "a", 0, 10)
    assert st.check_and_record("seal", "b", 0, 50)
    t[0] = 11.0  # "a" expired, "b" live
    assert st.check_and_record("seal", "c", 11, 50) is True
    assert st.check_and_record("seal", "b", 11, 50) is False
    assert st.stats() == {"entries": 2, "max_entries": 2, "nonce_store_full": 0, "reclaimed": 1}


def test_store_stays_bounded():
    # (c) never exceeds max_entries no matter the pressure.
    t = [0.0]
    st = InMemoryNonceStore(max_entries=50, clock=lambda: t[0])
    full = 0
    for i in range(1000):
        t[0] = i * 0.5
        try:
            st.check_and_record("seal", f"n{i}", t[0], 40)
        except NonceStoreFull:
            full += 1
        assert len(st) <= 50
    assert full > 0 and st.nonce_store_full == full
    assert st.stats()["reclaimed"] > 0


def test_full_counter_emitted_to_metrics_collector():
    from skeleton.observability.metrics import MetricsCollector

    m = MetricsCollector()
    st = InMemoryNonceStore(max_entries=1, clock=lambda: 0.0, metrics=m)
    st.check_and_record("seal", "a", 0, 5)
    with pytest.raises(NonceStoreFull):
        st.check_and_record("seal", "b", 0, 5)
    snap = m.snapshot()
    assert any("nonce_store_full" in k and v == 1 for k, v in snap["counters"].items()), snap


def test_max_entries_from_env(monkeypatch):
    assert max_entries_from_env({}) == 100_000
    assert max_entries_from_env({"SKELETON_SEAL_NONCE_STORE_MAX": "250"}) == 250
    for bad in ("0", "-1", "lots"):
        with pytest.raises(ValueError):
            max_entries_from_env({"SKELETON_SEAL_NONCE_STORE_MAX": bad})
    monkeypatch.setenv("SKELETON_SEAL_NONCE_STORE_MAX", "7")
    assert InMemoryNonceStore.from_env().max_entries == 7
    mw = RequestSealMiddleware(lambda *a: None, policy=GatePolicy())
    assert mw.nonce_store.max_entries == 7


def test_verify_seal_propagates_store_full_not_auth_error():
    st = InMemoryNonceStore(max_entries=1, clock=lambda: NOW)
    assert _v(_mint(), cache=st) == "svc"
    with pytest.raises(NonceStoreFull):
        _v(_mint(), cache=st)


def test_middleware_store_full_503_retry_after(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    monkeypatch.delenv("GF_SEAL_KEYRING", raising=False)
    monkeypatch.delenv("GF_SEAL_LEGACY", raising=False)
    monkeypatch.setenv("SKELETON_SEAL_NONCE_STORE_MAX", "1")
    app = FastAPI()

    @app.post("/api/v1/projects/{pid}")
    async def write(pid: str, who: str = Depends(hs.require_seal)):
        return {"pid": pid}

    app.add_middleware(RequestSealMiddleware, policy=GatePolicy())
    c = TestClient(app)
    url, body = "/api/v1/projects/p1?b=2&a=1", b'{"x":1}'
    h1 = {"x-gf-seal": _live(), "x-gf-tenant": "t1"}
    assert c.post(url, content=body, headers=h1).status_code == 200
    r = c.post(url, content=body, headers={"x-gf-seal": _live(), "x-gf-tenant": "t1"})
    assert r.status_code == 503 and r.json() == {"error": "nonce_store_full"}
    assert int(r.headers["retry-after"]) >= 1
    r = c.post(url, content=body, headers=h1)  # replay of the live nonce still 401
    assert r.status_code == 401 and r.json() == {"error": "invalid_seal"}


def test_nonce_store_thread_safe_single_winner():
    import threading

    st = InMemoryNonceStore()
    wins = []
    ths = [threading.Thread(target=lambda: wins.append(st.check_and_record("seal", "z", 0, 1e12))) for _ in range(32)]
    for th in ths:
        th.start()
    for th in ths:
        th.join()
    assert wins.count(True) == 1


def test_nonce_store_satisfies_protocol():
    store: NonceStore = InMemoryNonceStore()
    assert store.check_and_record("seal", "p", time.time(), 5)


def test_nonce_store_rejects_nonfinite_and_unbounded_replay_evidence():
    st = InMemoryNonceStore(clock=lambda: NOW)
    for bad in (float("nan"), float("inf"), float("-inf"), True, "1"):
        assert st.check_and_record("seal", "n", bad, 60) is False
        assert st.check_and_record("seal", "n", NOW, bad) is False
    for bad in ("", "x" * 257, "line\nfeed"):
        assert st.check_and_record("seal", bad, NOW, 60) is False
        assert st.check_and_record(bad, "nonce", NOW, 60) is False
    assert len(st) == 0
    with pytest.raises(ValueError, match="bounded"):
        max_entries_from_env({MAX_ENTRIES_ENV: "1000001"})
