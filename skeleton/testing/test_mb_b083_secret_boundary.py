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


def test_secret_diagnostics_reject_unbounded_artifacts_and_audit_logs(monkeypatch):
    with pytest.raises(m.ContractError, match="scan input"):
        m.scan("x" * (m.MAX_ARTIFACT_CHARS + 1))
    with pytest.raises(m.ContractError, match="artifact collection"):
        m.evaluate({str(i): "safe" for i in range(m.MAX_ARTIFACTS + 1)}, [])
    for bad in (True, -1, "0"):
        with pytest.raises(m.ContractError):
            m.Credential("bad", ("read",), bad, 10)
    c = m.Credential("ci", ("read",), 0, 100)
    ledger = m.CredentialLedger()
    monkeypatch.setattr(m, "MAX_AUDIT_EVENTS", 1)
    assert ledger.use(c, "read", 1)
    with pytest.raises(m.ContractError, match="audit log"):
        ledger.use(c, "read", 2)
