"""Signed correlated trust snapshot tests."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from skeleton.shells.ai.audit_witness import AuditWitnessVerification
from skeleton.shells.ai.authority_health import (
    AuthorityHealthReport,
    AuthorityHealthResult,
    AuthorityHealthState,
)
from skeleton.shells.ai.runtime_trust import (
    RuntimeTrustEpoch,
    RuntimeTrustReport,
    RuntimeTrustSurface,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.ai.trust_snapshot import (
    AITrustSnapshot,
    AITrustSnapshotBuilder,
    SignedAITrustSnapshot,
)


def fp(char: str) -> str:
    return hashlib.sha256(char.encode()).hexdigest()


def runtime_report(*, release=fp("r")):
    surface = RuntimeTrustSurface(
        "rev",
        fp("p"),
        fp("t"),
        fp("e"),
    )
    epoch = RuntimeTrustEpoch(
        1,
        surface,
        release_evidence_digest=release,
        release_id="release",
        release_revision=1,
        release_channel_revision=1,
    )
    return RuntimeTrustReport(True, (), epoch)


def health_report(*, ok=True):
    result = AuthorityHealthResult(
        "seal",
        AuthorityHealthState.HEALTHY if ok else AuthorityHealthState.UNAVAILABLE,
        10,
        0.01,
    )
    return AuthorityHealthReport(
        ok,
        (result,),
        () if ok else ("required authority dependency seal is unavailable",),
        fp("h"),
        10,
    )


def witness_report(*, ok=True):
    return AuditWitnessVerification(
        ok,
        () if ok else ("signature invalid",),
        4,
        fp("w"),
        fp("a"),
    )


def builder(clock=lambda: 20):
    return AITrustSnapshotBuilder(
        ArtifactSigner("trust-key", b"k" * 32, clock=clock),
        clock=clock,
    )


def test_trust_snapshot_builds_signed_correlated_artifact():
    item = builder().build(
        service_phase="ready",
        runtime_trust=runtime_report(),
        authority_health=health_report(),
        audit_witness=witness_report(),
        sandbox_binding_digest=fp("s"),
    )
    assert item.snapshot.service_phase == "ready"
    assert item.snapshot.runtime_trust_digest == runtime_report().epoch.digest
    assert item.snapshot.authority_health_policy_digest == fp("h")
    assert item.snapshot.audit_witness_head_digest == fp("w")
    assert item.snapshot.audit_witness_sequence == 4
    assert item.snapshot.release_evidence_digest == fp("r")
    assert item.snapshot.sandbox_binding_digest == fp("s")
    assert item.signature.artifact_type == "ai-trust-snapshot"
    assert item.signature.artifact_digest == item.snapshot.digest


def test_trust_snapshot_digest_is_deterministic():
    item = AITrustSnapshot(
        1,
        "ready",
        fp("t"),
        fp("h"),
        fp("w"),
        1,
        fp("r"),
        fp("s"),
        10,
    )
    assert len(item.digest) == 64
    assert item.digest == item.digest


@pytest.mark.parametrize(
    "field,value",
    [
        ("service_phase", "degraded"),
        ("runtime_trust_digest", fp("u")),
        ("authority_health_policy_digest", fp("i")),
        ("audit_witness_head_digest", fp("x")),
        ("audit_witness_sequence", 2),
        ("release_evidence_digest", fp("q")),
        ("sandbox_binding_digest", fp("z")),
        ("observed_at", 11),
    ],
)
def test_snapshot_digest_changes_for_every_bound_surface(field, value):
    original = AITrustSnapshot(
        1,
        "ready",
        fp("t"),
        fp("h"),
        fp("w"),
        1,
        fp("r"),
        fp("s"),
        10,
    )
    changed = replace(original, **{field: value})
    assert original.digest != changed.digest


def test_builder_allows_no_audit_witness():
    item = builder().build(
        service_phase="ready",
        runtime_trust=runtime_report(),
        authority_health=health_report(),
    )
    assert item.snapshot.audit_witness_head_digest == ""
    assert item.snapshot.audit_witness_sequence == 0


def test_builder_rejects_denied_runtime_trust():
    report = RuntimeTrustReport(False, ("drift",), None)
    with pytest.raises(RuntimeError, match="runtime trust"):
        builder().build(
            service_phase="degraded",
            runtime_trust=report,
            authority_health=health_report(),
        )


def test_builder_rejects_unhealthy_authority_by_default():
    with pytest.raises(RuntimeError, match="authority health"):
        builder().build(
            service_phase="degraded",
            runtime_trust=runtime_report(),
            authority_health=health_report(ok=False),
        )


def test_builder_can_capture_unhealthy_authority_for_incident_evidence():
    item = builder().build(
        service_phase="degraded",
        runtime_trust=runtime_report(),
        authority_health=health_report(ok=False),
        require_healthy=False,
    )
    assert item.snapshot.service_phase == "degraded"


def test_builder_rejects_failed_audit_verification():
    with pytest.raises(RuntimeError, match="audit witness"):
        builder().build(
            service_phase="ready",
            runtime_trust=runtime_report(),
            authority_health=health_report(),
            audit_witness=witness_report(ok=False),
        )


def test_verify_happy_path():
    target = builder()
    item = target.build(
        service_phase="ready",
        runtime_trust=runtime_report(),
        authority_health=health_report(),
        audit_witness=witness_report(),
    )
    target.verify(
        item,
        expected_runtime_trust_digest=item.snapshot.runtime_trust_digest,
        expected_audit_head_digest=fp("w"),
        expected_release_evidence_digest=fp("r"),
    )


def test_verify_runtime_epoch_mismatch():
    target = builder()
    item = target.build(
        service_phase="ready",
        runtime_trust=runtime_report(),
        authority_health=health_report(),
    )
    with pytest.raises(RuntimeError, match="runtime epoch"):
        target.verify(
            item,
            expected_runtime_trust_digest=fp("x"),
        )


def test_verify_audit_head_mismatch():
    target = builder()
    item = target.build(
        service_phase="ready",
        runtime_trust=runtime_report(),
        authority_health=health_report(),
        audit_witness=witness_report(),
    )
    with pytest.raises(RuntimeError, match="audit witness"):
        target.verify(item, expected_audit_head_digest=fp("x"))


def test_verify_release_mismatch():
    target = builder()
    item = target.build(
        service_phase="ready",
        runtime_trust=runtime_report(),
        authority_health=health_report(),
    )
    with pytest.raises(RuntimeError, match="release evidence"):
        target.verify(item, expected_release_evidence_digest=fp("x"))


def test_signature_tamper_is_detected():
    target = builder()
    item = target.build(
        service_phase="ready",
        runtime_trust=runtime_report(),
        authority_health=health_report(),
    )
    bad_signature = replace(item.signature, signature="0" * 64)
    tampered = SignedAITrustSnapshot(item.snapshot, bad_signature)
    assert not target.inspect_signature(tampered)


def test_snapshot_payload_tamper_with_old_signature_is_detected():
    target = builder()
    item = target.build(
        service_phase="ready",
        runtime_trust=runtime_report(),
        authority_health=health_report(),
    )
    tampered_snapshot = replace(item.snapshot, service_phase="degraded")
    with pytest.raises(ValueError, match="digest mismatch"):
        SignedAITrustSnapshot(tampered_snapshot, item.signature)


def test_snapshot_to_dict_has_no_signing_key_material():
    target = builder()
    item = target.build(
        service_phase="ready",
        runtime_trust=runtime_report(),
        authority_health=health_report(),
    )
    data = item.to_dict()
    assert data["snapshot_digest"] == item.snapshot.digest
    assert data["signature"]["key_id"] == "trust-key"
    assert "key" not in data["signature"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"schema_version": 2},
        {"service_phase": ""},
        {"runtime_trust_digest": "bad"},
        {"authority_health_policy_digest": "bad"},
        {"audit_witness_head_digest": "bad", "audit_witness_sequence": 1},
        {"release_evidence_digest": "bad"},
        {"sandbox_binding_digest": "bad"},
        {"audit_witness_sequence": -1},
        {"observed_at": -1},
    ],
)
def test_snapshot_validation(kwargs):
    values = dict(
        schema_version=1,
        service_phase="ready",
        runtime_trust_digest=fp("t"),
        authority_health_policy_digest=fp("h"),
        audit_witness_head_digest="",
        audit_witness_sequence=0,
        release_evidence_digest="",
        sandbox_binding_digest="",
        observed_at=1,
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        AITrustSnapshot(**values)


def test_witness_digest_requires_nonzero_sequence():
    with pytest.raises(ValueError, match="present together"):
        AITrustSnapshot(
            1,
            "ready",
            fp("t"),
            fp("h"),
            fp("w"),
            0,
        )


def test_witness_sequence_requires_digest():
    with pytest.raises(ValueError, match="present together"):
        AITrustSnapshot(
            1,
            "ready",
            fp("t"),
            fp("h"),
            "",
            1,
        )


def test_signed_snapshot_rejects_wrong_artifact_type():
    snapshot = AITrustSnapshot(
        1,
        "ready",
        fp("t"),
        fp("h"),
    )
    signature = ArtifactSigner("k", b"x" * 32).sign(
        "wrong",
        snapshot.digest,
    )
    with pytest.raises(ValueError, match="artifact type"):
        SignedAITrustSnapshot(snapshot, signature)


def test_builder_clock_is_bound_into_snapshot():
    now = [1.0]
    target = builder(clock=lambda: now[0])
    first = target.build(
        service_phase="ready",
        runtime_trust=runtime_report(),
        authority_health=health_report(),
    )
    now[0] = 2.0
    second = target.build(
        service_phase="ready",
        runtime_trust=runtime_report(),
        authority_health=health_report(),
    )
    assert first.snapshot.observed_at == 1.0
    assert second.snapshot.observed_at == 2.0
    assert first.snapshot.digest != second.snapshot.digest
