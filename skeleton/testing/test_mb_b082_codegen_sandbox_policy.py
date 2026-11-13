import pytest
from skeleton.mass_build.b081_b100 import b082_codegen_sandbox_policy as m
def pol(**g): return m.SandboxPolicy(g, m.Quota(100, 64, 1000))
def test_deny_by_default():
    p = pol()
    assert not p.decide("fs_read", "/etc/passwd") and not p.decide("network", "x.com")
def test_prefix_grants_are_path_safe():
    p = pol(fs_write=("/work/out",))
    assert p.decide("fs_write", "/work/out/a.txt") and not p.decide("fs_write", "/work/outside")
def test_evaluate_and_quota():
    p = pol(fs_read=("/work",))
    assert m.evaluate(p, [("fs_read", "/etc"), ("network", "evil")]).passed
    assert not m.evaluate(p, [("fs_read", "/work/x")]).passed
    assert not m.evaluate(pol(process=("sh",)), []).passed
    assert p.within_quota(100, 64, 1000) and not p.within_quota(101, 1, 1)
def test_bad_input():
    with pytest.raises(m.ContractError): pol(gpu=("x",))
    with pytest.raises(m.ContractError): m.Quota(0, 1, 1)
