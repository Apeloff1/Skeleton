import pytest
from skeleton.mass_build.b081_b100 import b083_secret_boundary as m
def test_scan_detects():
    assert m.scan("key AKIA" + "A" * 16) and m.scan("token = abcdefghijk") and not m.scan("hello world")
def test_ledger_scoped_and_expiring():
    c = m.Credential("ci", ("read",), 0, 100); L = m.CredentialLedger()
    assert L.use(c, "read", 5) and not L.use(c, "write", 5) and not L.use(c, "read", 100)
    assert [e[2] for e in L.events] == ["read:ok", "write:deny", "read:deny"]
def test_evaluate():
    good = m.Credential("a", ("read",), 0, 60)
    assert m.evaluate({"log.txt": "ok"}, [good]).passed
    v = m.evaluate({"b.log": "password: hunter2hunter2"}, [m.Credential("w", ("*",), 0, 99999)])
    assert set(v.findings) == {"secret:b.log:pattern3", "long_lived:w", "wildcard_scope:w"}
def test_bad_credential():
    with pytest.raises(m.ContractError): m.Credential("x", (), 5, 5)
