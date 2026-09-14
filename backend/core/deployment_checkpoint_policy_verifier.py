"""Policy-bound offline verification for deployment checkpoint witness proofs.

The low-level proof verifiers intentionally accept quorum/freshness as explicit
arguments. This module closes the higher-level policy-binding seam: once an auditor
pins a trust-policy manifest digest, proof verification derives quorum, freshness,
continuity mode, and witness-registry identity from that manifest instead of accepting
parallel caller-supplied policy values that could drift from the pinned authority.
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
    """Verify an anchored append-only advance when continuity is not mandatory.

    A trust-advance packet authenticates the old anchor but does not independently
    witness the new endpoint. It therefore cannot satisfy a policy that explicitly
    requires witnessed continuity at both endpoints.
    """
    registry = _policy_ready(
        manifest,
        expected_manifest_sha256=expected_manifest_sha256,
        trusted_witnesses=trusted_witnesses,
    )
    if registry is None or manifest.continuity_required:
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
    """Return whether a proof family can satisfy the pinned deployment policy.

    This is capability classification only; it does not verify a proof packet.
    """
    if proof_kind not in {"pin", "trust_advance", "witnessed_continuity"}:
        return False
    if not manifest.required:
        return True
    if manifest.continuity_required:
        return proof_kind == "witnessed_continuity"
    return proof_kind in {"pin", "trust_advance", "witnessed_continuity"}
