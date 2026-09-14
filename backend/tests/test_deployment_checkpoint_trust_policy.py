from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from core.canonical_json import canonical_json_clone
from core.deployment_checkpoint_pin_config import DeploymentCheckpointPinPolicy
from core.deployment_checkpoint_trust_policy import (
    build_deployment_checkpoint_trust_policy_manifest,
    decode_deployment_checkpoint_trust_policy_manifest,
    verify_deployment_checkpoint_trust_policy_manifest,
    verify_deployment_checkpoint_trust_registry,
)
from core.transparency_witness import TrustedWitness
from tests.test_deployment_checkpoint_pin_runtime import _keypair, _trusted


def _policy(*, required_groups=2, max_age_seconds=300, required=True, continuity=False):
    _, witnesses = _trusted()
    return DeploymentCheckpointPinPolicy(
        witnesses,
        required_groups,
        max_age_seconds,
        required,
        continuity,
    )


def test_manifest_is_stable_and_verifies_only_against_pinned_digest():
    policy = _policy()
    manifest = build_deployment_checkpoint_trust_policy_manifest(policy)
    assert len(manifest.manifest_sha256) == 64
    assert verify_deployment_checkpoint_trust_policy_manifest(
        manifest,
        expected_manifest_sha256=manifest.manifest_sha256,
    ) is True
    assert verify_deployment_checkpoint_trust_policy_manifest(
        manifest,
        expected_manifest_sha256="f" * 64,
    ) is False


def test_manifest_is_order_independent_but_registry_binding_is_exact():
    policy = _policy()
    manifest = build_deployment_checkpoint_trust_policy_manifest(policy)
    reordered = DeploymentCheckpointPinPolicy(
        tuple(reversed(policy.witnesses)),
        policy.required_groups,
        policy.max_age_seconds,
        policy.required,
        policy.continuity_required,
    )
    assert build_deployment_checkpoint_trust_policy_manifest(reordered) == manifest
    assert verify_deployment_checkpoint_trust_registry(manifest, policy.witnesses) is True
    assert verify_deployment_checkpoint_trust_registry(manifest, reordered.witnesses) is True


def test_key_rotation_changes_manifest_and_old_registry_no_longer_matches():
    policy = _policy()
    manifest = build_deployment_checkpoint_trust_policy_manifest(policy)
    _, replacement_public = _keypair()
    rotated_rows = list(policy.witnesses)
    rotated_rows[0] = TrustedWitness(
        rotated_rows[0].id,
        rotated_rows[0].independence_group,
        True,
        replacement_public,
    )
    rotated_policy = DeploymentCheckpointPinPolicy(
        tuple(rotated_rows),
        policy.required_groups,
        policy.max_age_seconds,
        policy.required,
        policy.continuity_required,
    )
    rotated = build_deployment_checkpoint_trust_policy_manifest(rotated_policy)
    assert rotated.manifest_sha256 != manifest.manifest_sha256
    assert verify_deployment_checkpoint_trust_registry(manifest, rotated_policy.witnesses) is False
    assert verify_deployment_checkpoint_trust_registry(rotated, rotated_policy.witnesses) is True


def test_quorum_freshness_and_continuity_changes_rotate_policy_identity():
    base = build_deployment_checkpoint_trust_policy_manifest(_policy())
    quorum = build_deployment_checkpoint_trust_policy_manifest(_policy(required_groups=1))
    freshness = build_deployment_checkpoint_trust_policy_manifest(_policy(max_age_seconds=301))
    continuity = build_deployment_checkpoint_trust_policy_manifest(_policy(continuity=True))
    assert len({
        base.manifest_sha256,
        quorum.manifest_sha256,
        freshness.manifest_sha256,
        continuity.manifest_sha256,
    }) == 4


def test_manifest_tampering_and_python_type_confusion_fail_closed():
    manifest = build_deployment_checkpoint_trust_policy_manifest(_policy())
    tampered = replace(manifest, required_groups=1)
    assert verify_deployment_checkpoint_trust_policy_manifest(
        tampered,
        expected_manifest_sha256=manifest.manifest_sha256,
    ) is False
    bool_version = replace(manifest, version=True)
    assert verify_deployment_checkpoint_trust_policy_manifest(
        bool_version,
        expected_manifest_sha256=manifest.manifest_sha256,
    ) is False


def test_disabled_witnesses_do_not_enter_active_policy_identity():
    _, witnesses = _trusted()
    _, extra_public = _keypair()
    with_disabled = DeploymentCheckpointPinPolicy(
        witnesses + (TrustedWitness("disabled", "org-c", False, extra_public),),
        2,
        300,
        True,
        False,
    )
    active_only = DeploymentCheckpointPinPolicy(witnesses, 2, 300, True, False)
    assert (
        build_deployment_checkpoint_trust_policy_manifest(with_disabled)
        == build_deployment_checkpoint_trust_policy_manifest(active_only)
    )


def test_json_policy_manifest_round_trip_preserves_identity():
    manifest = build_deployment_checkpoint_trust_policy_manifest(_policy(continuity=True))
    raw = canonical_json_clone(asdict(manifest))
    decoded = decode_deployment_checkpoint_trust_policy_manifest(raw)
    assert decoded == manifest
    assert verify_deployment_checkpoint_trust_policy_manifest(
        decoded,
        expected_manifest_sha256=manifest.manifest_sha256,
    ) is True


def test_policy_wire_rejects_unknown_fields_nonarrays_and_bool_integer_confusion():
    manifest = build_deployment_checkpoint_trust_policy_manifest(_policy())
    raw = canonical_json_clone(asdict(manifest))
    raw["server_authoritative"] = True
    with pytest.raises(ValueError, match="schema mismatch"):
        decode_deployment_checkpoint_trust_policy_manifest(raw)

    raw = canonical_json_clone(asdict(manifest))
    raw["witnesses"] = tuple(raw["witnesses"])
    with pytest.raises(ValueError, match="JSON array"):
        decode_deployment_checkpoint_trust_policy_manifest(raw)

    raw = canonical_json_clone(asdict(manifest))
    raw["required_groups"] = True
    with pytest.raises(ValueError, match="quorum malformed"):
        decode_deployment_checkpoint_trust_policy_manifest(raw)


def test_policy_wire_rejects_witness_text_fingerprint_and_digest_tampering():
    manifest = build_deployment_checkpoint_trust_policy_manifest(_policy())
    raw = canonical_json_clone(asdict(manifest))
    raw["witnesses"][0]["id"] = " " + raw["witnesses"][0]["id"]
    with pytest.raises(ValueError, match="canonical non-empty text"):
        decode_deployment_checkpoint_trust_policy_manifest(raw)

    raw = canonical_json_clone(asdict(manifest))
    raw["witnesses"][0]["public_key_fingerprint"] = "F" * 64
    with pytest.raises(ValueError, match="fingerprint malformed"):
        decode_deployment_checkpoint_trust_policy_manifest(raw)

    raw = canonical_json_clone(asdict(manifest))
    raw["manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="integrity failed"):
        decode_deployment_checkpoint_trust_policy_manifest(raw)
