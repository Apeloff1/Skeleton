import pytest
from skeleton.mass_build.b081_b100 import b087_capabilities as m
def test_grant_check_revoke():
    r = m.CapabilityRegistry("s"); c = r.grant("p", "read", "save")
    assert r.check(c.token, "p", "read", "save") and not r.check(c.token, "p", "write", "save")
    r.revoke(c.token); assert not r.check(c.token, "p", "read", "save")
    with pytest.raises(m.ContractError): r.revoke(c.token)
def test_deterministic_tokens():
    a, b = m.CapabilityRegistry("s"), m.CapabilityRegistry("s")
    assert a.grant("p", "r", "x").token == b.grant("p", "r", "x").token
def test_wildcards_rejected_and_bulk_revoke():
    r = m.CapabilityRegistry("s")
    with pytest.raises(m.ContractError): r.grant("p", "*", "x")
    r.grant("p", "a", "x"); r.grant("p", "b", "x"); r.grant("q", "a", "x")
    assert r.revoke_holder("p") == 2 and r.live == 1
    assert [e[0] for e in r.audit].count("revoke") == 2
