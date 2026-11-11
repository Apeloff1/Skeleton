import pytest
from skeleton.api.v1_edge.auth import ApiKeyStore, EdgeAuthenticator, SessionVerifier
from skeleton.api.v1_edge.envelope import EdgeError
from skeleton.api.v1_edge.registry import RouteSpec


def scope(**h):
    return {"headers": [(k.replace("_", "-").encode(), v.encode()) for k, v in h.items()]}


def test_api_key_lifecycle():
    now = [100.0]
    ks = ApiKeyStore(clock=lambda: now[0])
    tok = ks.add("a", "p" * 32, subject="s", tenant="t", scopes={"x"}, ttl_s=10)
    assert ks.verify(tok).tenant == "t"
    assert ks.verify(tok + "x") is None
    assert ks.verify("skk_zz.pw") is None
    assert ks.verify("nope") is None
    now[0] = 111
    assert ks.verify(tok) is None
    tok2 = ks.add("b", "p" * 32, subject="s", tenant="t")
    assert ks.revoke("b") and ks.verify(tok2) is None
    assert not ks.revoke("missing")
    with pytest.raises(ValueError):
        ks.add("a.b", "p" * 32, subject="s", tenant="t")


def test_session_roundtrip_tamper_expiry():
    now = [0.0]
    sv = SessionVerifier(b"k" * 16, clock=lambda: now[0])
    v = sv.issue("u", "t", ["a", "b"], ttl_s=5)
    p = sv.verify(v)
    assert p.scopes == {"a", "b"} and p.method == "session"
    assert sv.verify(v.replace("|t|", "|evil|")) is None
    assert sv.verify("garbage") is None
    now[0] = 6
    assert sv.verify(v) is None
    with pytest.raises(ValueError):
        sv.issue("u|x", "t")
    with pytest.raises(ValueError):
        SessionVerifier(b"short")


def test_enforce_policy_binding():
    ks = ApiKeyStore()
    tok = ks.add("a", "p" * 32, subject="s", tenant="t", scopes={"r"})
    a = EdgeAuthenticator(ks, SessionVerifier(b"k" * 16))
    with pytest.raises(EdgeError) as e:
        a.enforce(RouteSpec("GET", "/x"), scope())
    assert e.value.status == 401
    with pytest.raises(EdgeError) as e:
        a.enforce(RouteSpec("GET", "/x", scopes={"w"}), scope(x_api_key=tok))
    assert e.value.status == 403 and e.value.context["missing"] == ["w"]
    with pytest.raises(EdgeError) as e:
        a.enforce(RouteSpec("GET", "/x", auth="session"), scope(x_api_key=tok))
    assert e.value.code == "EDGE.AUTH.METHOD"
    assert a.enforce(RouteSpec("GET", "/x"), scope(authorization="Bearer " + tok)).subject == "s"
    assert a.enforce(RouteSpec("GET", "/x", auth="public"), scope(x_api_key="bad")).method == "anonymous"
