"""
Enterprise tests. Gateway request, rate limit, config validation, observability.
"""
import pytest
from skeleton.local_ai.enterprise_gateway import get_gateway
from skeleton.local_ai.enterprise_config import EnterpriseConfig
from skeleton.local_ai.local_ai_index import SEAMS
from skeleton.local_ai.version import __seams__
import importlib.util

def test_enterprise_request():
    gw = get_gateway()
    out = gw.request("enterprise test", "valid_cas_string_32chars_long_enough")
    assert out["status"] == "ok"
    assert out["health"]["healthy"] is True

def test_enterprise_seam_inventory():
    """Do not report healthy by inventing or silently lowering seam requirements."""
    assert __seams__ == 50
    assert len(SEAMS) == __seams__
    assert len(SEAMS) == len(set(SEAMS))
    for module in ("enterprise_auth", "enterprise_gateway", "enterprise_policy",
                   "enterprise_observability", "enterprise_sla"):
        assert module in SEAMS
        assert importlib.util.find_spec(f"skeleton.local_ai.{module}") is not None

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
