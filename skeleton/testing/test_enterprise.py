"""
Enterprise tests. Gateway request, rate limit, config validation, observability.
"""
import pytest
from skeleton.local_ai.enterprise_gateway import get_gateway
from skeleton.local_ai.enterprise_config import EnterpriseConfig

def test_enterprise_request():
    gw = get_gateway()
    out = gw.request("enterprise test", "valid_cas_string_32chars_long_enough")
    assert out["status"] == "ok"
    # A successful gateway request does not override actual runtime health.
    health = out["health"]
    assert health["healthy"] is (health["engine"] and health["doctor"] == "passed")

def test_enterprise_config():
    cfg = EnterpriseConfig()
    loaded = cfg.load()
    assert loaded["cas_min_length"] >= 16
    assert loaded["rate_capacity"] == 120

def test_rate_limit_reject():
    gw = get_gateway()
    # Force low capacity for test
    gw.limiter.capacity = 1
    gw.limiter.tokens = 0
    with pytest.raises(PermissionError):
        gw.request("x", "valid_cas_string_32chars_long_enough")
