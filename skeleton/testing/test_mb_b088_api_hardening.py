from skeleton.mass_build.b081_b100 import b088_api_hardening as m
def B(): return m.Boundary(b"k", {"u": frozenset({"buy"})}, rate_per_window=2)
def call(b, nonce, now=0, body=None, **kw):
    body = body or {"x": 1}
    return b.handle(principal=kw.pop("principal", "u"), action=kw.pop("action", "buy"), body=body, nonce=nonce,
                    ts=now, now=now, sig=kw.pop("sig", b.sign(body, nonce, now)), **kw)
def test_authz_bounds_sig():
    b = B()
    assert call(b, "n0", principal="x")[0] == 403
    assert call(b, "n1", body={"x": "a" * 5000})[0] == 413
    assert call(b, "n2", sig="bad")[0] == 401
def test_replay_and_rate():
    b = B()
    assert call(b, "n1")[0] == 200 and call(b, "n1")[0] == 409
    assert call(b, "n2")[0] == 200 and call(b, "n3")[0] == 429
    assert call(b, "n4", now=20)[0] == 200
def test_idempotency():
    b = m.Boundary(b"k", {"u": frozenset({"buy"})})
    r1 = call(b, "a", idem_key="k1"); r2 = call(b, "b", idem_key="k1", body={"x": 2})
    assert r1 == r2
