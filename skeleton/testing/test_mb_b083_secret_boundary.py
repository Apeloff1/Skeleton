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


def test_secret_evidence_rejects_control_and_bidi_diagnostic_labels():
    for bad in ("log" + chr(10) + "forged", "log" + chr(27) + "[31m", "log" + chr(0x202e) + "fake"):
        with pytest.raises(m.ContractError, match="artifact path"):
            m.evaluate({bad: "safe"}, [])
        with pytest.raises(m.ContractError, match="credential name"):
            m.Credential(bad, ("read",), 0, 60)
        with pytest.raises(m.ContractError, match="credential scopes"):
            m.Credential("valid", (bad,), 0, 60)
        ledger = m.CredentialLedger()
        with pytest.raises(m.ContractError, match="audit scope"):
            ledger.use(m.Credential("valid", ("read",), 0, 60), bad, 1)
        assert not ledger.events


def test_secret_audit_refuses_unbounded_timestamp_and_untyped_credential():
    for bad in (10**1000, m.MAX_AUDIT_TIMESTAMP + 1):
        with pytest.raises(m.ContractError, match="lifetime"):
            m.Credential("ci", ("read",), 0, bad)
    cred = m.Credential("ci", ("read",), 0, 100)
    ledger = m.CredentialLedger()
    with pytest.raises(m.ContractError, match="audit time"):
        ledger.use(cred, "read", 10**1000)
    with pytest.raises(m.ContractError, match="credential"):
        ledger.use(object(), "read", 1)
    assert not ledger.events


def test_credential_name_cannot_embed_secret_or_log_delimiters():
    for bad in ("password=supersecret123", "token: secretvalue",
                "name with spaces", "x\\tfield", "=malformed"):
        with pytest.raises(m.ContractError, match="credential name"):
            m.Credential(bad, ("read",), 0, 60)
    assert m.Credential("ci-runner:release_1", ("read",), 0, 60).name == "ci-runner:release_1"
