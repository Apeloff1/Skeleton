"""Policy-bound offline verification for deployment checkpoint witness proofs.

The low-level proof verifiers intentionally accept quorum/freshness as explicit
arguments. This module closes the higher-level policy-binding seam: once an auditor
pins a trust-policy manifest digest, proof verification derives quorum, freshness,
continuity mode, and witness-registry identity from that manifest instead of accepting
parallel caller-supplied policy values that could drift from the pinned authority.

The package dispatcher additionally enforces an exact context contract per proof kind,
so callers cannot accidentally verify a continuity packet with pin semantics or leave
unused trust inputs dangling beside the authoritative verification path.
"""
from __future__ import annotations

from typing import Iterable

from core.deployment_checkpoint_trust_advance import (
    DeploymentCheckpointTrustAdvance,
    verify_deployment_checkpoint_trust_advance,
)
from core.deployment_checkpoint_trust_policy import (
    DeploymentCheckpointTrustPolicyManifest,
    verify_deployment_checkpoint_trust_policy_manifest,
    verify_deployment_checkpoint_trust_registry,
)
from core.deployment_checkpoint_verification_package import (
    PROOF_PIN,
    PROOF_TRUST_ADVANCE,
    PROOF_WITNESSED_CONTINUITY,
    DeploymentCheckpointVerificationPackage,
    verify_deployment_checkpoint_verification_package,
)
from core.deployment_checkpoint_witness import (
    DeploymentCheckpointPinBundle,
    verify_deployment_checkpoint_pin_bundle,
)
from core.deployment_checkpoint_witnessed_continuity import (
    DeploymentCheckpointWitnessedContinuity,
    verify_deployment_checkpoint_witnessed_continuity,
)
from core.transparency_witness import TrustedWitness


def _policy_ready(
    manifest: DeploymentCheckpointTrustPolicyManifest,
    *,
    expected_manifest_sha256: str,
    trusted_witnesses: Iterable[TrustedWitness],
) -> tuple[TrustedWitness, ...] | None:
    registry = tuple(trusted_witnesses)
    if not verify_deployment_checkpoint_trust_policy_manifest(
        manifest,
        expected_manifest_sha256=expected_manifest_sha256,
    ):
        return None
    if not verify_deployment_checkpoint_trust_registry(manifest, registry):
        return None
    return registry


def verify_policy_bound_checkpoint_pin(
    bundle: DeploymentCheckpointPinBundle,
    *,
    manifest: DeploymentCheckpointTrustPolicyManifest,
    expected_manifest_sha256: str,
    trusted_witnesses: Iterable[TrustedWitness],
    expected_publication_sha256: str,
    verified_at: str,
) -> bool:
    """Verify one witnessed checkpoint strictly under a pinned policy identity."""
    registry = _policy_ready(
        manifest,
        expected_manifest_sha256=expected_manifest_sha256,
        trusted_witnesses=trusted_witnesses,
    )
    if registry is None:
        return False
    return verify_deployment_checkpoint_pin_bundle(
        bundle,
        trusted_witnesses=registry,
        expected_publication_head_sha256=expected_publication_sha256,
        expected_required_groups=manifest.required_groups,
        verified_at=verified_at,
        max_age_seconds=manifest.max_age_seconds,
    )


def verify_policy_bound_trust_advance(
    packet: DeploymentCheckpointTrustAdvance,
    *,
    manifest: DeploymentCheckpointTrustPolicyManifest,
    expected_manifest_sha256: str,
    trusted_witnesses: Iterable[TrustedWitness],
    anchor_verified_at: str,
    expected_current_publication_sha256: str,
) -> bool:
    """Verify an anchored append-only audit advance under a pinned optional policy.

    A trust-advance packet authenticates an older witnessed anchor and proves an
    append-only extension to an externally supplied current head. It does *not* place
    a fresh witness signature on that current head. Therefore it is useful as audit
    evidence only and cannot satisfy a policy whose ``required`` flag demands fresh
    current-head witness quorum.
    """
    registry = _policy_ready(
        manifest,
        expected_manifest_sha256=expected_manifest_sha256,
        trusted_witnesses=trusted_witnesses,
    )
    if registry is None or manifest.required:
        return False
    return verify_deployment_checkpoint_trust_advance(
        packet,
        trusted_witnesses=registry,
        expected_required_groups=manifest.required_groups,
        anchor_verified_at=anchor_verified_at,
        expected_current_publication_sha256=expected_current_publication_sha256,
        witness_max_age_seconds=manifest.max_age_seconds,
    )


def verify_policy_bound_witnessed_continuity(
    packet: DeploymentCheckpointWitnessedContinuity,
    *,
    manifest: DeploymentCheckpointTrustPolicyManifest,
    expected_manifest_sha256: str,
    trusted_witnesses: Iterable[TrustedWitness],
    previous_verified_at: str,
    current_verified_at: str,
    expected_previous_publication_sha256: str,
    expected_current_publication_sha256: str,
) -> bool:
    """Verify two independently witnessed epochs plus their append-only extension."""
    registry = _policy_ready(
        manifest,
        expected_manifest_sha256=expected_manifest_sha256,
        trusted_witnesses=trusted_witnesses,
    )
    if registry is None:
        return False
    return verify_deployment_checkpoint_witnessed_continuity(
        packet,
        trusted_witnesses=registry,
        expected_required_groups=manifest.required_groups,
        previous_verified_at=previous_verified_at,
        current_verified_at=current_verified_at,
        expected_previous_publication_sha256=expected_previous_publication_sha256,
        expected_current_publication_sha256=expected_current_publication_sha256,
        witness_max_age_seconds=manifest.max_age_seconds,
    )


def policy_satisfied_by_proof_kind(
    manifest: DeploymentCheckpointTrustPolicyManifest,
    proof_kind: str,
) -> bool:
    """Conservatively classify proof families without inspecting a concrete proof.

    A continuity-required policy returns only ``witnessed_continuity`` here because a
    bare kind does not reveal whether a pin targets genesis. Use
    :func:`proof_satisfies_policy` when a concrete proof packet is available.
    """
    if proof_kind not in {PROOF_PIN, PROOF_TRUST_ADVANCE, PROOF_WITNESSED_CONTINUITY}:
        return False
    if not manifest.required:
        return True
    if manifest.continuity_required:
        return proof_kind == PROOF_WITNESSED_CONTINUITY
    return proof_kind in {PROOF_PIN, PROOF_WITNESSED_CONTINUITY}


def proof_satisfies_policy(
    manifest: DeploymentCheckpointTrustPolicyManifest,
    proof_kind: str,
    proof: object,
) -> bool:
    """Classify one concrete proof against deployment witness policy semantics.

    Continuity has one intentional genesis exception shared with the runtime: the first
    publication has no earlier epoch to bridge, so a fresh witnessed pin on publication
    sequence 1 establishes the initial external trust anchor. From publication 2 onward
    a continuity-required policy accepts only a two-endpoint witnessed-continuity proof.
    """
    if proof_kind == PROOF_PIN:
        if not isinstance(proof, DeploymentCheckpointPinBundle):
            return False
        if not manifest.required:
            return True
        if manifest.continuity_required:
            return proof.publication_sequence == 1
        return True
    if proof_kind == PROOF_TRUST_ADVANCE:
        return isinstance(proof, DeploymentCheckpointTrustAdvance) and not manifest.required
    if proof_kind == PROOF_WITNESSED_CONTINUITY:
        return isinstance(proof, DeploymentCheckpointWitnessedContinuity)
    return False


def verify_policy_bound_verification_package(
    package: DeploymentCheckpointVerificationPackage,
    *,
    expected_manifest_sha256: str,
    trusted_witnesses: Iterable[TrustedWitness],
    expected_current_publication_sha256: str,
    pin_verified_at: str | None = None,
    anchor_verified_at: str | None = None,
    expected_previous_publication_sha256: str | None = None,
    previous_verified_at: str | None = None,
    current_verified_at: str | None = None,
) -> bool:
    """Verify one canonical package under an externally pinned trust policy.

    Exact proof-specific context is mandatory:

    * ``pin``: ``pin_verified_at`` only.
    * ``trust_advance``: ``anchor_verified_at`` only, and only when witnessing is optional.
    * ``witnessed_continuity``: previous head plus previous/current verification times.

    Supplying extra context fails closed. This makes the dispatcher a single
    unambiguous offline-verification boundary instead of a convenience wrapper that
    could silently ignore security-relevant caller inputs.
    """
    if not verify_deployment_checkpoint_verification_package(package):
        return False
    if not proof_satisfies_policy(
        package.policy_manifest,
        package.proof_kind,
        package.proof,
    ):
        return False

    manifest = package.policy_manifest
    common = {
        "manifest": manifest,
        "expected_manifest_sha256": expected_manifest_sha256,
        "trusted_witnesses": trusted_witnesses,
    }

    if package.proof_kind == PROOF_PIN:
        if (
            pin_verified_at is None
            or anchor_verified_at is not None
            or expected_previous_publication_sha256 is not None
            or previous_verified_at is not None
            or current_verified_at is not None
        ):
            return False
        if not isinstance(package.proof, DeploymentCheckpointPinBundle):
            return False
        return verify_policy_bound_checkpoint_pin(
            package.proof,
            expected_publication_sha256=expected_current_publication_sha256,
            verified_at=pin_verified_at,
            **common,
        )

    if package.proof_kind == PROOF_TRUST_ADVANCE:
        if (
            anchor_verified_at is None
            or pin_verified_at is not None
            or expected_previous_publication_sha256 is not None
            or previous_verified_at is not None
            or current_verified_at is not None
        ):
            return False
        if not isinstance(package.proof, DeploymentCheckpointTrustAdvance):
            return False
        return verify_policy_bound_trust_advance(
            package.proof,
            anchor_verified_at=anchor_verified_at,
            expected_current_publication_sha256=expected_current_publication_sha256,
            **common,
        )

    if package.proof_kind == PROOF_WITNESSED_CONTINUITY:
        if (
            expected_previous_publication_sha256 is None
            or previous_verified_at is None
            or current_verified_at is None
            or pin_verified_at is not None
            or anchor_verified_at is not None
        ):
            return False
        if not isinstance(package.proof, DeploymentCheckpointWitnessedContinuity):
            return False
        return verify_policy_bound_witnessed_continuity(
            package.proof,
            previous_verified_at=previous_verified_at,
            current_verified_at=current_verified_at,
            expected_previous_publication_sha256=expected_previous_publication_sha256,
            expected_current_publication_sha256=expected_current_publication_sha256,
            **common,
        )

    return False
