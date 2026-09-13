import pytest
from skeleton.frontier.gameforge_router import HealthRouter

def test_router_excludes_unhealthy_targets():
 r=HealthRouter(("a","b")); r.mark("a",False); assert r.next()=="b"; assert r.healthy==("b",)

def test_router_rejects_unknown_target():
 with pytest.raises(KeyError): HealthRouter(("a",)).mark("x",False)

def test_router_fails_when_all_unhealthy():
 r=HealthRouter(("a",)); r.mark("a",False); assert r.next() is None
