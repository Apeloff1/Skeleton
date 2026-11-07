"""Seal v2: domain binding + nonce replay protection (Jenkins seal finding).

Negative tests for every misuse: cross-domain, replay, tampered domain/nonce,
expired, missing nonce, legacy flag, keyring rotation.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skeleton.api import hmac_seal as hs
from skeleton.api.middleware import AuthError, GatePolicy, RequestSealMiddleware
from skeleton.client import seal as client_seal

SECRET = "seal-v2-test-secret"
NOW = 1_700_000_000


def _v(token, **kw):
    kw.setdefault("secret", SECRET)
    kw.setdefault("keyring", "")
    kw.setdefault("now", NOW)
    kw.setdefault("enforce_domain", True)
    return hs.verify_seal(token, **kw)


def _mint(domain="projects", **kw):
    kw.setdefault("secret", SECRET)
    kw.setdefault("now", NOW)
    return hs.mint_seal("svc", 60, domain=domain, **kw)


def test_v2_roundtrip_and_wire_shape():
    tok = _mint(principal="user1")
    parts = tok.split(".")
    assert parts[0] == "v2" and len(parts) == 7
    assert parts[1:4] == ["user1", "svc", "projects"]
    assert _v(tok, domain="projects", replay_cache=hs.InMemoryReplayCache()) == "svc"


def test_cross_domain_seal_rejected():
    tok = _mint("projects")
    with pytest.raises(AuthError):
        _v(tok, domain="realtime", replay_cache=hs.InMemoryReplayCache())


def test_v2_on_unchartered_path_rejected():
    with pytest.raises(AuthError):
        _v(_mint("projects"), domain=None)


def test_replayed_nonce_rejected():
    cache = hs.InMemoryReplayCache()
    tok = _mint()
    assert _v(tok, domain="projects", replay_cache=cache) == "svc"
    with pytest.raises(AuthError):
        _v(tok, domain="projects", replay_cache=cache)


def test_same_nonce_other_principal_is_separate_key_but_mac_bound():
    cache = hs.InMemoryReplayCache()
    a = hs.mint_seal_v2("svc", "projects", 60, secret=SECRET, now=NOW, principal="u1", nonce="n" * 32)
    b = hs.mint_seal_v2("svc", "projects", 60, secret=SECRET, now=NOW, principal="u2", nonce="n" * 32)
    assert _v(a, domain="projects", replay_cache=cache) == "svc"
    assert _v(b, domain="projects", replay_cache=cache) == "svc"


@pytest.mark.parametrize("idx,new", [(3, "realtime"), (5, "f" * 32), (1, "mallory"), (4, str(NOW + 30))])
def test_tampered_fields_rejected(idx, new):
    parts = _mint().split(".")
    parts[idx] = new
    with pytest.raises(AuthError):
        _v(".".join(parts), domain=parts[3], replay_cache=hs.InMemoryReplayCache())


def test_expired_seal_rejected():
    tok = hs.mint_seal("svc", 10, domain="projects", secret=SECRET, now=NOW)
    with pytest.raises(AuthError):
        _v(tok, domain="projects", now=NOW + 11)


def test_far_future_expiry_rejected():
    tok = client_seal.mint_seal_token("svc", 60, secret=SECRET, now=NOW + 10_000, domain="projects")
    with pytest.raises(AuthError):
        _v(tok, domain="projects")


@pytest.mark.parametrize("nonce_field", ["", "short", "bad.nonce" ])
def test_v2_missing_or_bad_nonce_rejected(nonce_field):
    principal, attester, domain, expiry = "svc", "svc", "projects", NOW + 60
    for nonce in (nonce_field,):
        mac = hs._sign_v2(principal, attester, domain, expiry, nonce, SECRET.encode())
        tok = f"v2.{principal}.{attester}.{domain}.{expiry}.{nonce}.{mac}" if nonce else f"v2.{principal}.{attester}.{domain}.{expiry}.{mac}"
        with pytest.raises(AuthError):
            _v(tok, domain="projects")


def test_v2_prefix_never_falls_back_to_legacy():
    # A legacy 3-part seal whose attester starts with "v2." is not a v2 seal and is refused.
    tok = hs.mint_seal("v2.x", 60, secret=SECRET, now=NOW)
    with pytest.raises(AuthError):
        _v(tok, domain="projects")


@pytest.mark.parametrize(
    "policy,domain,ok",
    [
        ("sensitive", "projects", True),
        ("sensitive", "realtime", False),
        ("allow", "realtime", True),
        ("deny", "projects", False),
        ("bogus", "projects", False),  # unknown value fails closed to deny
    ],
)
def test_legacy_flag(monkeypatch, policy, domain, ok):
    monkeypatch.setenv("GF_SEAL_LEGACY", policy)
    for tok in (
        hs.mint_seal("svc", 60, secret=SECRET, now=NOW),
        hs.mint_seal("svc", 60, secret=SECRET, now=NOW, principal="u1"),
    ):
        if ok:
            assert _v(tok, domain=domain) == "svc"
        else:
            with pytest.raises(AuthError):
                _v(tok, domain=domain)


def test_legacy_default_is_sensitive(monkeypatch):
    monkeypatch.delenv("GF_SEAL_LEGACY", raising=False)
    assert hs.legacy_policy() == "sensitive"
    assert not hs.legacy_allowed("realtime") and hs.legacy_allowed("projects")


def test_direct_helper_semantics_unchanged_without_enforce():
    legacy = hs.mint_seal("svc", 60, secret=SECRET, now=NOW)
    assert hs.verify_seal(legacy, secret=SECRET, now=NOW) == "svc"


def test_keyring_rotation_v2(monkeypatch):
    monkeypatch.delenv("GF_SEAL_SECRET", raising=False)
    old = hs.mint_seal("svc", 60, domain="projects", secret="old-key", now=NOW)
    new = hs.mint_seal("svc", 60, domain="projects", secret="new-key", now=NOW)
    ring = "k1=new-key,k0=old-key"
    cache = hs.InMemoryReplayCache()
    assert hs.verify_seal(old, secret="", keyring=ring, now=NOW, domain="projects", replay_cache=cache, enforce_domain=True) == "svc"
    assert hs.verify_seal(new, secret="", keyring=ring, now=NOW, domain="projects", replay_cache=cache, enforce_domain=True) == "svc"
    with pytest.raises(AuthError):
        hs.verify_seal(old, secret="", keyring="k1=new-key", now=NOW, domain="projects", enforce_domain=True)


def test_replay_cache_bounded_fails_closed_and_purges():
    cache = hs.InMemoryReplayCache(max_entries=2)
    assert cache.check_and_store("a", NOW + 10, NOW)
    assert cache.check_and_store("b", NOW + 10, NOW)
    with pytest.raises(hs.ReplayCacheFull):
        cache.check_and_store("c", NOW + 10, NOW)
    assert cache.check_and_store("c", NOW + 100, NOW + 11)  # a, b expired -> purged
    assert len(cache) == 1
    tok = _mint()
    full = hs.InMemoryReplayCache(max_entries=1)
    full.check_and_store("x", NOW + 999, NOW)
    with pytest.raises(AuthError):  # cache full -> fail closed (401)
        _v(tok, domain="projects", replay_cache=full)


def test_client_and_server_v2_byte_parity():
    kw = dict(secret=SECRET, now=NOW, principal="u1", domain="realtime", nonce="a" * 32)
    assert client_seal.mint_seal_token("svc", 60, **kw) == hs.mint_seal_v2("svc", "realtime", 60, secret=SECRET, now=NOW, principal="u1", nonce="a" * 32)


def test_client_sealer_v2_is_single_use():
    sealer = client_seal.RequestSealer("svc", seal_secret=SECRET, domain="projects", clock=lambda: NOW)
    a, b = sealer.token(), sealer.token()
    assert a != b and a.startswith("v2.") and b.startswith("v2.")


# --- middleware: domain resolved from GatePolicy, nonce consumed ---------------------------


@pytest.fixture()
def gated(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    monkeypatch.delenv("GF_SEAL_KEYRING", raising=False)
    monkeypatch.delenv("GF_SEAL_LEGACY", raising=False)
    app = FastAPI()

    @app.get("/api/v1/projects")
    def projects():
        return {"ok": True}

    @app.get("/api/v1/presence")
    def presence():
        return {"ok": True}

    app.add_middleware(RequestSealMiddleware, policy=GatePolicy())
    return TestClient(app)


def _h(domain):
    return {"x-gf-seal": hs.mint_seal("svc", 60, domain=domain, secret=SECRET)}


def test_middleware_v2_ok_then_replay_401(gated):
    h = _h("projects")
    assert gated.get("/api/v1/projects", headers=h).status_code == 200
    r = gated.get("/api/v1/projects", headers=h)
    assert r.status_code == 401 and r.json() == {"error": "invalid_seal"}


def test_middleware_cross_domain_401(gated):
    r = gated.get("/api/v1/presence", headers=_h("projects"))
    assert r.status_code == 401 and r.json() == {"error": "invalid_seal"}
    assert gated.get("/api/v1/presence", headers=_h("realtime")).status_code == 200


def test_middleware_legacy_default_rejected_on_realtime_only(gated):
    legacy = {"x-gf-seal": hs.mint_seal("svc", 60, secret=SECRET)}
    assert gated.get("/api/v1/projects", headers=legacy).status_code == 200
    assert gated.get("/api/v1/presence", headers=legacy).status_code == 401


def test_middleware_legacy_allow_flag(gated, monkeypatch):
    monkeypatch.setenv("GF_SEAL_LEGACY", "allow")
    legacy = {"x-gf-seal": hs.mint_seal("svc", 60, secret=SECRET)}
    assert gated.get("/api/v1/presence", headers=legacy).status_code == 200
