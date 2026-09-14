from __future__ import annotations

from dataclasses import asdict

from core.canonical_json import canonical_json_clone
from core.deployment_checkpoint_pin_config import DeploymentCheckpointPinPolicy
from core.deployment_checkpoint_policy_rotation import (
    build_deployment_checkpoint_policy_rotation,
    decode_deployment_checkpoint_policy_rotation,
    deployment_checkpoint_policy_rotation_weakens_security,
    sign_deployment_checkpoint_policy_rotation_approval,
    verify_deployment_checkpoint_policy_rotation,
)
from core.deployment_checkpoint_trust_policy import build_deployment_checkpoint_trust_policy_manifest
from core.transparency_witness import TrustedWitness
from tests.test_deployment_checkpoint_pin_runtime import _keypair


def _material(prefix: str):
    keys = [_keypair(), _keypair()]
    witnesses = (
        TrustedWitness(f"{prefix}-a", "org-a", True, keys[0][1]),
        TrustedWitness(f"{prefix}-b", "org-b", True, keys[1][1]),
    )
    return keys, witnesses


def _manifest(witnesses, *, groups=2, age=300, required=True, continuity=True):
    return build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, groups, age, required, continuity)
    )


def _rotation(*, stamp="2026-09-14T20:00:00+00:00", new_groups=2, new_age=300,
              new_required=True, new_continuity=True):
    old_keys, old_witnesses = _material("old")
    new_keys, new_witnesses = _material("new")
    old_manifest = _manifest(old_witnesses)
    new_manifest = _manifest(
        new_witnesses,
        groups=new_groups,
        age=new_age,
        required=new_required,
        continuity=new_continuity,
    )
    old_approvals = tuple(
        sign_deployment_checkpoint_policy_rotation_approval(
            role="old",
            old_manifest=old_manifest,
            new_manifest=new_manifest,
            private_key_b64=old_keys[i][0],
            public_key_b64=old_keys[i][1],
            witness_id=old_witnesses[i].id,
            independence_group=old_witnesses[i].independence_group,
            observed_at=stamp,
            nonce=f"old-{i}",
        )
        for i in range(2)
    )
    new_approvals = tuple(
        sign_deployment_checkpoint_policy_rotation_approval(
            role="new",
            old_manifest=old_manifest,
            new_manifest=new_manifest,
            private_key_b64=new_keys[i][0],
            public_key_b64=new_keys[i][1],
            witness_id=new_witnesses[i].id,
            independence_group=new_witnesses[i].independence_group,
            observed_at=stamp,
            nonce=f"new-{i}",
        )
        for i in range(2)
    )
    rotation = build_deployment_checkpoint_policy_rotation(
        old_manifest=old_manifest,
        new_manifest=new_manifest,
        old_approvals=old_approvals,
        new_approvals=new_approvals,
    )
    return old_witnesses, new_witnesses, old_manifest, new_manifest, rotation


def test_dual_quorum_rotation_advances_pinned_policy_identity():
    old_witnesses, new_witnesses, old_manifest, new_manifest, rotation = _rotation()
    assert old_manifest.manifest_sha256 != new_manifest.manifest_sha256
    assert verify_deployment_checkpoint_policy_rotation(
        rotation,
        expected_old_manifest_sha256=old_manifest.manifest_sha256,
        old_trusted_witnesses=old_witnesses,
        new_trusted_witnesses=new_witnesses,
        verified_at="2026-09-14T20:01:00+00:00",
    ) is True


def test_rotation_requires_exact_old_pin_and_new_key_registry():
    old_witnesses, new_witnesses, old_manifest, _, rotation = _rotation()
    assert verify_deployment_checkpoint_policy_rotation(
        rotation,
        expected_old_manifest_sha256="f" * 64,
        old_trusted_witnesses=old_witnesses,
        new_trusted_witnesses=new_witnesses,
        verified_at="2026-09-14T20:01:00+00:00",
    ) is False

    _, replacement_public = _keypair()
    spliced = list(new_witnesses)
    spliced[0] = TrustedWitness(spliced[0].id, spliced[0].independence_group, True, replacement_public)
    assert verify_deployment_checkpoint_policy_rotation(
        rotation,
        expected_old_manifest_sha256=old_manifest.manifest_sha256,
        old_trusted_witnesses=old_witnesses,
        new_trusted_witnesses=tuple(spliced),
        verified_at="2026-09-14T20:01:00+00:00",
    ) is False


def test_rotation_approvals_expire_under_manifest_freshness():
    old_witnesses, new_witnesses, old_manifest, _, rotation = _rotation()
    assert verify_deployment_checkpoint_policy_rotation(
        rotation,
        expected_old_manifest_sha256=old_manifest.manifest_sha256,
        old_trusted_witnesses=old_witnesses,
        new_trusted_witnesses=new_witnesses,
        verified_at="2026-09-14T20:05:01+00:00",
    ) is False


def test_security_weakening_requires_explicit_auditor_opt_in():
    old_witnesses, new_witnesses, old_manifest, new_manifest, rotation = _rotation(
        new_age=600,
        new_continuity=False,
    )
    assert deployment_checkpoint_policy_rotation_weakens_security(old_manifest, new_manifest) is True
    common = dict(
        rotation=rotation,
        expected_old_manifest_sha256=old_manifest.manifest_sha256,
        old_trusted_witnesses=old_witnesses,
        new_trusted_witnesses=new_witnesses,
        verified_at="2026-09-14T20:01:00+00:00",
    )
    assert verify_deployment_checkpoint_policy_rotation(**common) is False
    assert verify_deployment_checkpoint_policy_rotation(
        **common,
        allow_policy_weakening=True,
    ) is True


def test_rotation_json_round_trip_preserves_transport_integrity():
    old_witnesses, new_witnesses, old_manifest, _, rotation = _rotation()
    decoded = decode_deployment_checkpoint_policy_rotation(
        canonical_json_clone(asdict(rotation))
    )
    assert decoded == rotation
    assert verify_deployment_checkpoint_policy_rotation(
        decoded,
        expected_old_manifest_sha256=old_manifest.manifest_sha256,
        old_trusted_witnesses=old_witnesses,
        new_trusted_witnesses=new_witnesses,
        verified_at="2026-09-14T20:01:00+00:00",
    ) is True


def test_rotation_wire_rejects_bool_version_and_package_tampering():
    _, _, _, _, rotation = _rotation()
    raw = canonical_json_clone(asdict(rotation))
    raw["version"] = True
    try:
        decode_deployment_checkpoint_policy_rotation(raw)
    except ValueError as exc:
        assert "version malformed" in str(exc)
    else:
        raise AssertionError("boolean rotation version was accepted")

    raw = canonical_json_clone(asdict(rotation))
    raw["rotation_sha256"] = "0" * 64
    try:
        decode_deployment_checkpoint_policy_rotation(raw)
    except ValueError as exc:
        assert "integrity failed" in str(exc)
    else:
        raise AssertionError("tampered rotation package was accepted")
