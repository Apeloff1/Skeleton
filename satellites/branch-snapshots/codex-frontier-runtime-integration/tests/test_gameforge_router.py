import pytest
from skeleton.frontier.gameforge_router import HealthRouter

def test_router_cycles_healthy_targets():
 r=HealthRouter(("a","b")); assert [r.next(),r.next(),r.next()]==["a","b","a"]

def test_router_skips_unhealthy_and_recovers():
 r=HealthRouter(("a","b")); r.mark("a",False); assert r.next()=="b"; r.mark("a",True); assert r.next()=="a"

def test_router_rejects_unknown_target():
 with pytest.raises(KeyError): HealthRouter(("a",)).mark("x",False)

def test_router_fails_when_all_unhealthy():
 r=HealthRouter(("a",)); r.mark("a",False); assert r.next() is None
