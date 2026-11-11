import asyncio
import pytest
from skeleton.api.v1_edge.envelope import EdgeError
from skeleton.api.v1_edge.health import HealthRegistry
from skeleton.api.v1_edge.security import CorsPolicy
from skeleton.api.v1_edge.webhook_ingress import WebhookIngressVerifier, sign

K = b"k" * 16


def test_webhook_verify_paths():
    now = [1000.0]
    v = WebhookIngressVerifier({"gh": K}, clock=lambda: now[0])
    sig = sign(K, 1000, b"{}")
    assert v.verify("gh", sig, b"{}") == 1000
    with pytest.raises(EdgeError) as e:
        v.verify("gh", sig, b"{}")
    assert e.value.code == "EDGE.WEBHOOK.REPLAY"
    for src, s, body, code in [("x", sig, b"{}", "EDGE.WEBHOOK.UNKNOWN_SOURCE"),
                               ("gh", None, b"{}", "EDGE.WEBHOOK.UNSIGNED"),
                               ("gh", "t=abc,v1=00", b"{}", "EDGE.WEBHOOK.BAD_SIGNATURE"),
                               ("gh", sign(K, 1000, b"[]"), b"{}", "EDGE.WEBHOOK.BAD_SIGNATURE"),
                               ("gh", sign(K, 1, b"{}"), b"{}", "EDGE.WEBHOOK.STALE")]:
        with pytest.raises(EdgeError) as e:
            v.verify(src, s, body)
        assert e.value.code == code


def test_webhook_rotation_multi_sig():
    v = WebhookIngressVerifier({"gh": K}, clock=lambda: 5)
    new = b"n" * 16
    v.rotate("gh", new)
    both = sign(new, 5, b"x") + ",v1=" + sign(K, 5, b"x").split("v1=")[1]
    assert v.verify("gh", both, b"x") == 5
    with pytest.raises(ValueError):
        v.rotate("gh", b"short")


def test_cors_policy():
    with pytest.raises(ValueError):
        CorsPolicy(frozenset({"*"}), allow_credentials=True)
    c = CorsPolicy(frozenset({"https://a"}), allow_credentials=True)
    assert not c.allowed("https://b") and not c.allowed(None)
    assert c.response_headers("https://a")["access-control-allow-credentials"] == "true"
    assert c.preflight_headers("https://a", "POST", "content-type") is not None
    assert c.preflight_headers("https://a", "TRACE", None) is None
    assert c.preflight_headers("https://a", "POST", "x-evil") is None


def test_health_ready_states():
    h = HealthRegistry(timeout_s=0.05)
    h.add("ok", lambda: True)
    h.add("opt", lambda: False, critical=False)
    assert asyncio.run(h.ready()) == (200, {"status": "degraded", "checks": {"ok": "ok", "opt": "fail"}})

    async def slow():
        await asyncio.sleep(1)
        return True

    def boom():
        raise RuntimeError
    h.add("slow", slow)
    h.add("boom", boom)
    code, body = asyncio.run(h.ready())
    assert code == 503 and body["checks"]["slow"] == "fail" and body["checks"]["boom"] == "fail"
    with pytest.raises(ValueError):
        h.add("ok", lambda: True)
    assert h.live()["status"] == "ok"
