"""Canonical transport package for policy-bound deployment checkpoint proofs.

The package is not a trust root. It carries a policy manifest and exactly one proof
family in a digest-bound JSON shape so offline tooling cannot silently splice a proof
kind, manifest, or nested packet during transport. Authority still comes from an
out-of-band pinned policy-manifest digest and trusted witness registry.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hmac
from typing import Any, Mapping, Union

from core.canonical_json import CanonicalJSONError, canonical_json_sha256
from core.deployment_checkpoint_trust_advance import DeploymentCheckpointTrustAdvance
from core.deployment_checkpoint_trust_policy import (
    DeploymentCheckpointTrustPolicyManifest,
    decode_deployment_checkpoint_trust_policy_manifest,
    verify_deployment_checkpoint_trust_policy_manifest,
)
from core.deployment_checkpoint_trust_wire import (
    decode_deployment_checkpoint_pin_bundle,
    decode_deployment_checkpoint_trust_advance,
    decode_deployment_checkpoint_witnessed_continuity,
)
from core.deployment_checkpoint_witness import DeploymentCheckpointPinBundle
from core.deployment_checkpoint_witnessed_continuity import DeploymentCheckpointWitnessedContinuity

DEPLOYMENT_CHECKPOINT_VERIFICATION_PACKAGE_VERSION = 1
PROOF_PIN = "pin"
PROOF_TRUST_ADVANCE = "trust_advance"
PROOF_WITNESSED_CONTINUITY = "witnessed_continuity"
_PROOF_KINDS = {PROOF_PIN, PROOF_TRUST_ADVANCE, PROOF_WITNESSED_CONTINUITY}
_PACKAGE_KEYS = {"version", "policy_manifest", "proof_kind", "proof", "package_sha256"}
Proof = Union[
    DeploymentCheckpointPinBundle,
    DeploymentCheckpointTrustAdvance,
    DeploymentCheckpointWitnessedContinuity,
]


@dataclass(frozen=True, slots=True)
class DeploymentCheckpointVerificationPackage:
    version: int
    policy_manifest: DeploymentCheckpointTrustPolicyManifest
    proof_kind: str
    proof: Proof
    package_sha256: str


def _proof_matches(kind: str, proof: Any) -> bool:
    return (
        (kind == PROOF_PIN and isinstance(proof, DeploymentCheckpointPinBundle))
        or (kind == PROOF_TRUST_ADVANCE and isinstance(proof, DeploymentCheckpointTrustAdvance))
        or (
            kind == PROOF_WITNESSED_CONTINUITY
            and isinstance(proof, DeploymentCheckpointWitnessedContinuity)
        )
    )


def _payload(package: DeploymentCheckpointVerificationPackage) -> dict[str, Any]:
    return {
        "version": package.version,
        "policy_manifest": asdict(package.policy_manifest),
        "proof_kind": package.proof_kind,
        "proof": asdict(package.proof),
    }


def build_deployment_checkpoint_verification_package(
    *,
    policy_manifest: DeploymentCheckpointTrustPolicyManifest,
    proof_kind: str,
    proof: Proof,
) -> DeploymentCheckpointVerificationPackage:
    if not isinstance(policy_manifest, DeploymentCheckpointTrustPolicyManifest):
        raise ValueError("policy_manifest must be a DeploymentCheckpointTrustPolicyManifest")
    if proof_kind not in _PROOF_KINDS or not _proof_matches(proof_kind, proof):
        raise ValueError("deployment checkpoint verification proof kind/type mismatch")
    if not verify_deployment_checkpoint_trust_policy_manifest(
        policy_manifest,
        expected_manifest_sha256=policy_manifest.manifest_sha256,
    ):
        raise ValueError("deployment checkpoint verification policy manifest is invalid")
    draft = DeploymentCheckpointVerificationPackage(
        DEPLOYMENT_CHECKPOINT_VERIFICATION_PACKAGE_VERSION,
        policy_manifest,
        proof_kind,
        proof,
        "",
    )
    digest = canonical_json_sha256(_payload(draft))
    return DeploymentCheckpointVerificationPackage(
        draft.version,
        draft.policy_manifest,
        draft.proof_kind,
        draft.proof,
        digest,
    )


def verify_deployment_checkpoint_verification_package(
    package: DeploymentCheckpointVerificationPackage,
) -> bool:
    """Verify package transport integrity only; this does not establish trust authority."""
    try:
        if not isinstance(package, DeploymentCheckpointVerificationPackage):
            return False
        if (
            type(package.version) is not int
            or package.version != DEPLOYMENT_CHECKPOINT_VERIFICATION_PACKAGE_VERSION
        ):
            return False
        if package.proof_kind not in _PROOF_KINDS:
            return False
        if not _proof_matches(package.proof_kind, package.proof):
            return False
        if not verify_deployment_checkpoint_trust_policy_manifest(
            package.policy_manifest,
            expected_manifest_sha256=package.policy_manifest.manifest_sha256,
        ):
            return False
        if (
            not isinstance(package.package_sha256, str)
            or len(package.package_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in package.package_sha256)
        ):
            return False
        expected = canonical_json_sha256(_payload(package))
        return hmac.compare_digest(expected, package.package_sha256)
    except (CanonicalJSONError, TypeError, ValueError):
        return False


def decode_deployment_checkpoint_verification_package(
    raw: Any,
) -> DeploymentCheckpointVerificationPackage:
    if not isinstance(raw, Mapping) or set(raw) != _PACKAGE_KEYS:
        raise ValueError("deployment checkpoint verification package schema mismatch")
    version = raw.get("version")
    if (
        type(version) is not int
        or version != DEPLOYMENT_CHECKPOINT_VERIFICATION_PACKAGE_VERSION
    ):
        raise ValueError("deployment checkpoint verification package version malformed")
    kind = raw.get("proof_kind")
    if not isinstance(kind, str) or kind not in _PROOF_KINDS:
        raise ValueError("deployment checkpoint verification proof kind malformed")
    digest = raw.get("package_sha256")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(ch not in "0123456789abcdef" for ch in digest)
    ):
        raise ValueError("deployment checkpoint verification package digest malformed")
    manifest = decode_deployment_checkpoint_trust_policy_manifest(raw.get("policy_manifest"))
    proof_raw = raw.get("proof")
    if kind == PROOF_PIN:
        proof: Proof = decode_deployment_checkpoint_pin_bundle(proof_raw)
    elif kind == PROOF_TRUST_ADVANCE:
        proof = decode_deployment_checkpoint_trust_advance(proof_raw)
    else:
        proof = decode_deployment_checkpoint_witnessed_continuity(proof_raw)
    package = DeploymentCheckpointVerificationPackage(version, manifest, kind, proof, digest)
    if not verify_deployment_checkpoint_verification_package(package):
        raise ValueError("deployment checkpoint verification package integrity failed")
    return package
