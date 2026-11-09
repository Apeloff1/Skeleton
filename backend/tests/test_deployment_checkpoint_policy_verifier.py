from __future__ import annotations

from dataclasses import replace

from core.deployment_checkpoint_pin_config import DeploymentCheckpointPinPolicy
from core.deployment_checkpoint_policy_verifier import (
    policy_satisfied_by_proof_kind,
    verify_policy_bound_checkpoint_pin,
    verify_policy_bound_trust_advance,
    verify_policy_bound_witnessed_continuity,
)
from core.deployment_checkpoint_trust_advance import build_deployment_checkpoint_trust_advance
from core.deployment_checkpoint_trust_policy import build_deployment_checkpoint_trust_policy_manifest
from core.transparency_witness import TrustedWitness
from tests.test_deployment_checkpoint_pin_runtime import _keypair
from tests.test_deployment_checkpoint_trust_advance import _deploy, _gateway, _witnessed_anchor
from tests.test_deployment_checkpoint_witnessed_continuity import _continuity


def test_pinned_policy_drives_witnessed_continuity_verification(tmp_path):
    _, _, witnesses, previous, current, packet = _continuity(tmp_path)
    manifest = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 2, 300, True, True)
    )

    assert verify_policy_bound_witnessed_continuity(
        packet,
        manifest=manifest,
        expected_manifest_sha256=manifest.manifest_sha256,
        trusted_witnesses=witnesses,
        previous_verified_at="2026-09-14T20:01:00+00:00",
        current_verified_at="2026-09-14T20:06:00+00:00",
        expected_previous_publication_sha256=previous.sha256,
        expected_current_publication_sha256=current.sha256,
    ) is True


def test_policy_digest_and_registry_rotation_are_external_authority(tmp_path):
    _, _, witnesses, previous, current, packet = _continuity(tmp_path)
    manifest = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 2, 300, True, True)
    )
    common = dict(
        manifest=manifest,
        trusted_witnesses=witnesses,
        previous_verified_at="2026-09-14T20:01:00+00:00",
        current_verified_at="2026-09-14T20:06:00+00:00",
        expected_previous_publication_sha256=previous.sha256,
        expected_current_publication_sha256=current.sha256,
    )
    assert verify_policy_bound_witnessed_continuity(
        packet,
        expected_manifest_sha256="f" * 64,
        **common,
    ) is False

    _, replacement_public = _keypair()
    rotated = list(witnesses)
    rotated[0] = TrustedWitness(
        rotated[0].id,
        rotated[0].independence_group,
        True,
        replacement_public,
    )
    assert verify_policy_bound_witnessed_continuity(
        packet,
        expected_manifest_sha256=manifest.manifest_sha256,
        manifest=manifest,
        trusted_witnesses=tuple(rotated),
        previous_verified_at=common["previous_verified_at"],
        current_verified_at=common["current_verified_at"],
        expected_previous_publication_sha256=previous.sha256,
        expected_current_publication_sha256=current.sha256,
    ) is False


def test_manifest_freshness_is_used_instead_of_parallel_caller_policy(tmp_path):
    _, _, witnesses, previous, current, packet = _continuity(tmp_path)
    strict = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 2, 60, True, True)
    )
    relaxed = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 2, 600, True, True)
    )
    kwargs = dict(
        trusted_witnesses=witnesses,
        previous_verified_at="2026-09-14T20:02:00+00:00",
        current_verified_at="2026-09-14T20:06:00+00:00",
        expected_previous_publication_sha256=previous.sha256,
        expected_current_publication_sha256=current.sha256,
    )
    assert verify_policy_bound_witnessed_continuity(
        packet,
        manifest=strict,
        expected_manifest_sha256=strict.manifest_sha256,
        **kwargs,
    ) is False
    assert verify_policy_bound_witnessed_continuity(
        packet,
        manifest=relaxed,
        expected_manifest_sha256=relaxed.manifest_sha256,
        **kwargs,
    ) is True


def test_trust_advance_is_audit_only_when_current_witnessing_is_required(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    anchor = gateway.checkpoints.latest()
    assert anchor is not None
    witnesses, bundle = _witnessed_anchor(anchor)
    _deploy(gateway, "artifact-v2")
    current = gateway.checkpoints.latest()
    assert current is not None
    packet = build_deployment_checkpoint_trust_advance(
        pin_bundle=bundle,
        checkpoint_ledger=gateway.checkpoints,
    )

    optional = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 3, 300, False, False)
    )
    required = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 3, 300, True, False)
    )
    continuity = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 3, 300, True, True)
    )
    common = dict(
        trusted_witnesses=witnesses,
        anchor_verified_at="2026-09-14T20:01:00+00:00",
        expected_current_publication_sha256=current.sha256,
    )
    assert verify_policy_bound_trust_advance(
        packet,
        manifest=optional,
        expected_manifest_sha256=optional.manifest_sha256,
        **common,
    ) is True
    assert verify_policy_bound_trust_advance(
        packet,
        manifest=required,
        expected_manifest_sha256=required.manifest_sha256,
        **common,
    ) is False
    assert verify_policy_bound_trust_advance(
        packet,
        manifest=continuity,
        expected_manifest_sha256=continuity.manifest_sha256,
        **common,
    ) is False


def test_single_pin_uses_manifest_quorum_and_freshness(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    publication = gateway.checkpoints.latest()
    assert publication is not None
    witnesses, bundle = _witnessed_anchor(publication)
    manifest = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 3, 300, True, False)
    )
    assert verify_policy_bound_checkpoint_pin(
        bundle,
        manifest=manifest,
        expected_manifest_sha256=manifest.manifest_sha256,
        trusted_witnesses=witnesses,
        expected_publication_sha256=publication.sha256,
        verified_at="2026-09-14T20:01:00+00:00",
    ) is True

    changed_quorum = replace(manifest, required_groups=2)
    assert verify_policy_bound_checkpoint_pin(
        bundle,
        manifest=changed_quorum,
        expected_manifest_sha256=manifest.manifest_sha256,
        trusted_witnesses=witnesses,
        expected_publication_sha256=publication.sha256,
        verified_at="2026-09-14T20:01:00+00:00",
    ) is False


def test_proof_kind_capability_requires_fresh_current_witness_for_mandatory_policy():
    _, public_a = _keypair()
    _, public_b = _keypair()
    witnesses = (
        TrustedWitness("a", "org-a", True, public_a),
        TrustedWitness("b", "org-b", True, public_b),
    )
    required = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 2, 300, True, False)
    )
    continuity = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 2, 300, True, True)
    )
    optional = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 2, 300, False, False)
    )

    assert policy_satisfied_by_proof_kind(required, "pin") is True
    assert policy_satisfied_by_proof_kind(required, "trust_advance") is False
    assert policy_satisfied_by_proof_kind(required, "witnessed_continuity") is True
    assert policy_satisfied_by_proof_kind(continuity, "witnessed_continuity") is True
    assert policy_satisfied_by_proof_kind(continuity, "trust_advance") is False
    assert policy_satisfied_by_proof_kind(continuity, "pin") is False
    assert policy_satisfied_by_proof_kind(optional, "trust_advance") is True
    assert policy_satisfied_by_proof_kind(optional, "unknown") is False
