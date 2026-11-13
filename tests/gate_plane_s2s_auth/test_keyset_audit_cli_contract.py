import io
import json

import pytest

from skeleton.gate_plane.s2s.audit import AUDIT_METRIC, InMemoryAuditSink, S2SAuditTrail, TelemetryAuditSink
from skeleton.gate_plane.s2s.keyset import KeySetError, apply_keyset, export_keyset, validate_keyset, verifiable_kids
from skeleton.gate_plane.s2s.mint_cli import TEST_ONLY_MASTER, main, build_test_keyring
from skeleton.gate_plane.s2s.rotation import derived_secret_factory


def test_keyset_has_no_secrets_and_validates(ring):
    doc = export_keyset(ring, issuer="gate")
    validate_keyset(doc)
    blob = json.dumps(doc)
    assert derived_secret_factory(TEST_ONLY_MASTER)("test-k1").hex() not in blob
    bad = dict(doc, keys=[dict(doc["keys"][0], k="secret")])
    with pytest.raises(KeySetError):
        validate_keyset(bad)


def test_rotation_overlap_and_revocation_sync(clock):
    authority = build_test_keyring(["test-k1"], clock=clock)
    replica = build_test_keyring(["test-k1"], clock=clock)
    f = derived_secret_factory(TEST_ONLY_MASTER)
    for r in (authority, replica):
        r.rotate("test-k2", f("test-k2"), overlap_s=300)
    assert set(verifiable_kids(export_keyset(authority), clock.now())) == {"test-k1", "test-k2"}
    authority.revoke("test-k1", reason="leak")
    rep = apply_keyset(replica, export_keyset(authority))
    assert rep.revoked == ["test-k1"]
    assert replica.state_of("test-k1").value == "revoked"


def test_keyset_drift_fails_closed(clock):
    a = build_test_keyring(["test-k1"], clock=clock)
    b = build_test_keyring(["test-k1"], clock=clock)
    doc = export_keyset(a)
    doc["keys"][0]["fp"] = "0" * 16
    doc.pop("digest")
    rep = apply_keyset(b, doc)
    assert rep.drift == ["test-k1"] and rep.revoked == ["test-k1"]


class _Metrics:
    def __init__(self):
        self.calls = []

    def increment(self, name, value=1.0, labels=None):
        self.calls.append((name, labels))


class _Tel:
    def __init__(self):
        self.metrics = _Metrics()


def test_audit_via_telemetry_and_keyring(ring, clock):
    tel = _Tel()
    sink = InMemoryAuditSink()
    trail = S2SAuditTrail([sink, TelemetryAuditSink(tel)], clock=clock)
    assert trail.sync_keyring(ring) >= 1
    assert trail.sync_keyring(ring) == 0
    assert tel.metrics.calls and tel.metrics.calls[0][0] == AUDIT_METRIC
    assert all("path" not in labels for _, labels in tel.metrics.calls)


def test_cli_refuses_non_test_kid_and_roundtrips():
    out = io.StringIO()
    assert main(["mint", "--service", "svc-a", "--audience", "gate", "--kid", "prod-k1"], out=out) == 2
    out = io.StringIO()
    assert main(["mint", "--service", "svc-a", "--audience", "gate", "--scope", "forge:read", "--now", "1700000000"], out=out) == 0
    tok = out.getvalue().strip()
    out2 = io.StringIO()
    assert main(["verify", "--audience", "gate", "--now", "1700000001", tok], out=out2) == 0
    assert json.loads(out2.getvalue())["claims"]["iss"] == "svc-a"
