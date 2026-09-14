from __future__ import annotations

from core.deployment_checkpoint_pin_config import DeploymentCheckpointPinPolicy
from core.deployment_checkpoint_policy_verifier import verify_policy_bound_verification_package
from core.deployment_checkpoint_trust_advance import build_deployment_checkpoint_trust_advance
from core.deployment_checkpoint_trust_policy import build_deployment_checkpoint_trust_policy_manifest
from core.deployment_checkpoint_verification_package import (
    PROOF_PIN,
    PROOF_TRUST_ADVANCE,
    PROOF_WITNESSED_CONTINUITY,
    build_deployment_checkpoint_verification_package,
)
from core.transparency_witness import TrustedWitness
from tests.test_deployment_checkpoint_pin_runtime import _keypair
from tests.test_deployment_checkpoint_trust_advance import _deploy, _gateway, _witnessed_anchor
from tests.test_deployment_checkpoint_witnessed_continuity import _continuity


def _pin_package(tmp_path):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    publication = gateway.checkpoints.latest()
    assert publication is not None
    witnesses, bundle = _witnessed_anchor(publication)
    manifest = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 3, 300, True, False)
    )
    package = build_deployment_checkpoint_verification_package(
        policy_manifest=manifest,
        proof_kind=PROOF_PIN,
        proof=bundle,
    )
    return witnesses, manifest, publication, package


def _advance_package(tmp_path, *, required=False):
    gateway = _gateway(tmp_path)
    _deploy(gateway, "artifact-v1")
    anchor = gateway.checkpoints.latest()
    assert anchor is not None
    witnesses, bundle = _witnessed_anchor(anchor)
    _deploy(gateway, "artifact-v2")
    current = gateway.checkpoints.latest()
    assert current is not None
    proof = build_deployment_checkpoint_trust_advance(
        pin_bundle=bundle,
        checkpoint_ledger=gateway.checkpoints,
    )
    manifest = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 3, 300, required, False)
    )
    package = build_deployment_checkpoint_verification_package(
        policy_manifest=manifest,
        proof_kind=PROOF_TRUST_ADVANCE,
        proof=proof,
    )
    return witnesses, manifest, current, package


def _continuity_package(tmp_path):
    _, _, witnesses, previous, current, proof = _continuity(tmp_path)
    manifest = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 2, 300, True, True)
    )
    package = build_deployment_checkpoint_verification_package(
        policy_manifest=manifest,
        proof_kind=PROOF_WITNESSED_CONTINUITY,
        proof=proof,
    )
    return witnesses, manifest, previous, current, package


def test_dispatch_verifies_single_pin_with_exact_context(tmp_path):
    witnesses, manifest, publication, package = _pin_package(tmp_path)
    assert verify_policy_bound_verification_package(
        package,
        expected_manifest_sha256=manifest.manifest_sha256,
        trusted_witnesses=witnesses,
        expected_current_publication_sha256=publication.sha256,
        pin_verified_at="2026-09-14T20:01:00+00:00",
    ) is True


def test_dispatch_verifies_trust_advance_as_optional_audit_evidence(tmp_path):
    witnesses, manifest, current, package = _advance_package(tmp_path, required=False)
    assert verify_policy_bound_verification_package(
        package,
        expected_manifest_sha256=manifest.manifest_sha256,
        trusted_witnesses=witnesses,
        expected_current_publication_sha256=current.sha256,
        anchor_verified_at="2026-09-14T20:01:00+00:00",
    ) is True


def test_dispatch_rejects_trust_advance_for_required_current_head_witness_policy(tmp_path):
    witnesses, manifest, current, package = _advance_package(tmp_path, required=True)
    assert verify_policy_bound_verification_package(
        package,
        expected_manifest_sha256=manifest.manifest_sha256,
        trusted_witnesses=witnesses,
        expected_current_publication_sha256=current.sha256,
        anchor_verified_at="2026-09-14T20:01:00+00:00",
    ) is False


def test_dispatch_verifies_witnessed_continuity_with_both_endpoint_times(tmp_path):
    witnesses, manifest, previous, current, package = _continuity_package(tmp_path)
    assert verify_policy_bound_verification_package(
        package,
        expected_manifest_sha256=manifest.manifest_sha256,
        trusted_witnesses=witnesses,
        expected_current_publication_sha256=current.sha256,
        expected_previous_publication_sha256=previous.sha256,
        previous_verified_at="2026-09-14T20:01:00+00:00",
        current_verified_at="2026-09-14T20:06:00+00:00",
    ) is True


def test_dispatch_rejects_missing_or_extra_context_instead_of_ignoring_it(tmp_path):
    witnesses, manifest, publication, package = _pin_package(tmp_path)
    common = dict(
        package=package,
        expected_manifest_sha256=manifest.manifest_sha256,
        trusted_witnesses=witnesses,
        expected_current_publication_sha256=publication.sha256,
    )
    assert verify_policy_bound_verification_package(**common) is False
    assert verify_policy_bound_verification_package(
        **common,
        pin_verified_at="2026-09-14T20:01:00+00:00",
        anchor_verified_at="2026-09-14T20:01:00+00:00",
    ) is False


def test_dispatch_rejects_wrong_policy_pin_and_registry_splice(tmp_path):
    witnesses, manifest, publication, package = _pin_package(tmp_path)
    common = dict(
        package=package,
        trusted_witnesses=witnesses,
        expected_current_publication_sha256=publication.sha256,
        pin_verified_at="2026-09-14T20:01:00+00:00",
    )
    assert verify_policy_bound_verification_package(
        expected_manifest_sha256="f" * 64,
        **common,
    ) is False

    _, replacement_public = _keypair()
    spliced = list(witnesses)
    spliced[0] = TrustedWitness(
        spliced[0].id,
        spliced[0].independence_group,
        True,
        replacement_public,
    )
    assert verify_policy_bound_verification_package(
        package,
        expected_manifest_sha256=manifest.manifest_sha256,
        trusted_witnesses=tuple(spliced),
        expected_current_publication_sha256=publication.sha256,
        pin_verified_at="2026-09-14T20:01:00+00:00",
    ) is False


def test_continuity_policy_cannot_be_satisfied_by_trust_advance_package(tmp_path):
    witnesses, _, current, package = _advance_package(tmp_path, required=False)
    continuity_manifest = build_deployment_checkpoint_trust_policy_manifest(
        DeploymentCheckpointPinPolicy(witnesses, 3, 300, True, True)
    )
    # The package remains bound to its original optional manifest, so trying to
    # validate it against a stronger pinned policy fails before proof dispatch.
    assert verify_policy_bound_verification_package(
        package,
        expected_manifest_sha256=continuity_manifest.manifest_sha256,
        trusted_witnesses=witnesses,
        expected_current_publication_sha256=current.sha256,
        anchor_verified_at="2026-09-14T20:01:00+00:00",
    ) is False
