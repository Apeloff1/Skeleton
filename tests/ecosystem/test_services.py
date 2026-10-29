"""Microservice facade tests."""
from skeleton.jeeves.ecosystem.microservices.session_service import handle, health

def test_handle():
    r = handle({"op": "create", "payload": {"brief": "x"}})
    assert r["ok"] is True
    bad = handle({})
    assert bad["ok"] is False

def test_health():
    assert health()["ready"] is True
