"""Externally verifiable continuity between two independently witnessed checkpoint heads.

A trust-advance proof authenticates an old anchor and proves append-only history to a
new head. This stronger packet additionally requires an independent witness quorum on
the new head. The result binds two externally witnessed audit epochs with a verified
append-only suffix, making server-side split-history substitution detectable whenever
observers retain either witnessed endpoint.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hmac
import re
from typing import Any, Iterable

from core.canonical_json import CanonicalJSONError, canonical_json_sha256
from core.deployment_checkpoint_proof import (
    DeploymentCheckpointPublicationProof,
    build_deployment_checkpoint_publication_extension,
    verify_deployment_checkpoint_publication_extension,
)
from core.deployment_checkpoint_witness import (
    DeploymentCheckpointPinBundle,
    verify_deployment_checkpoint_pin_bundle,
)
from core.transparency_witness import TrustedWitness

DEPLOYMENT_CHECKPOINT_WITNESSED_CONTINUITY_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class DeploymentCheckpointWitnessedContinuity:
    version: int
    previous_publication_sha256: str
    current_publication_sha256: str
    previous_bundle: DeploymentCheckpointPinBundle
    current_bundle: DeploymentCheckpointPinBundle
    extension_proof: DeploymentCheckpointPublicationProof
    attestation_sha256: str


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _payload(packet: DeploymentCheckpointWitnessedContinuity) -> dict[str, Any]:
    return {
        "version": packet.version,
        "previous_publication_sha256": packet.previous_publication_sha256,
        "current_publication_sha256": packet.current_publication_sha256,
        "previous_bundle": asdict(packet.previous_bundle),
        "current_bundle": asdict(packet.current_bundle),
        "extension_proof": asdict(packet.extension_proof),
    }


def build_deployment_checkpoint_witnessed_continuity(
    *,
    previous_bundle: DeploymentCheckpointPinBundle,
    current_bundle: DeploymentCheckpointPinBundle,
    checkpoint_ledger,
) -> DeploymentCheckpointWitnessedContinuity:
    if not isinstance(previous_bundle, DeploymentCheckpointPinBundle):
        raise ValueError("previous_bundle must be a DeploymentCheckpointPinBundle")
    if not isinstance(current_bundle, DeploymentCheckpointPinBundle):
        raise ValueError("current_bundle must be a DeploymentCheckpointPinBundle")
    if previous_bundle.publication_sequence >= current_bundle.publication_sequence:
        raise ValueError("witnessed continuity requires a strictly newer current publication")
    extension = build_deployment_checkpoint_publication_extension(
        checkpoint_ledger,
        previous_bundle.publication_sha256,
    )
    if not extension.publications:
        raise ValueError("checkpoint continuity extension is empty")
    if not hmac.compare_digest(extension.publications[0].sha256, previous_bundle.publication_sha256):
        raise ValueError("previous witness bundle diverges from extension anchor")
    if not hmac.compare_digest(extension.publications[-1].sha256, current_bundle.publication_sha256):
        raise ValueError("current witness bundle does not describe the current publication head")
    draft = DeploymentCheckpointWitnessedContinuity(
        version=DEPLOYMENT_CHECKPOINT_WITNESSED_CONTINUITY_VERSION,
        previous_publication_sha256=previous_bundle.publication_sha256,
        current_publication_sha256=current_bundle.publication_sha256,
        previous_bundle=previous_bundle,
        current_bundle=current_bundle,
        extension_proof=extension,
        attestation_sha256="",
    )
    digest = canonical_json_sha256(_payload(draft))
    return DeploymentCheckpointWitnessedContinuity(
        draft.version,
        draft.previous_publication_sha256,
        draft.current_publication_sha256,
        draft.previous_bundle,
        draft.current_bundle,
        draft.extension_proof,
        digest,
    )


def verify_deployment_checkpoint_witnessed_continuity(
    packet: DeploymentCheckpointWitnessedContinuity,
    *,
    trusted_witnesses: Iterable[TrustedWitness],
    expected_required_groups: int,
    previous_verified_at: str,
    current_verified_at: str,
    expected_previous_publication_sha256: str,
    expected_current_publication_sha256: str,
    witness_max_age_seconds: int = 3600,
) -> bool:
    try:
        if not isinstance(packet, DeploymentCheckpointWitnessedContinuity):
            return False
        if type(packet.version) is not int or packet.version != DEPLOYMENT_CHECKPOINT_WITNESSED_CONTINUITY_VERSION:
            return False
        pins = (
            packet.previous_publication_sha256,
            packet.current_publication_sha256,
            packet.attestation_sha256,
            expected_previous_publication_sha256,
            expected_current_publication_sha256,
        )
        if not all(_is_sha(value) for value in pins):
            return False
        if not hmac.compare_digest(packet.previous_publication_sha256, expected_previous_publication_sha256):
            return False
        if not hmac.compare_digest(packet.current_publication_sha256, expected_current_publication_sha256):
            return False
        if packet.previous_bundle.publication_sequence >= packet.current_bundle.publication_sequence:
            return False
        if not hmac.compare_digest(packet.previous_bundle.publication_sha256, packet.previous_publication_sha256):
            return False
        if not hmac.compare_digest(packet.current_bundle.publication_sha256, packet.current_publication_sha256):
            return False
        if not packet.extension_proof.publications:
            return False
        if not hmac.compare_digest(packet.extension_proof.publications[0].sha256, packet.previous_publication_sha256):
            return False
        if not hmac.compare_digest(packet.extension_proof.publications[-1].sha256, packet.current_publication_sha256):
            return False
        if not verify_deployment_checkpoint_pin_bundle(
            packet.previous_bundle,
            trusted_witnesses=trusted_witnesses,
            expected_publication_head_sha256=expected_previous_publication_sha256,
            expected_required_groups=expected_required_groups,
            verified_at=previous_verified_at,
            max_age_seconds=witness_max_age_seconds,
        ):
            return False
        if not verify_deployment_checkpoint_pin_bundle(
            packet.current_bundle,
            trusted_witnesses=trusted_witnesses,
            expected_publication_head_sha256=expected_current_publication_sha256,
            expected_required_groups=expected_required_groups,
            verified_at=current_verified_at,
            max_age_seconds=witness_max_age_seconds,
        ):
            return False
        if not verify_deployment_checkpoint_publication_extension(
            packet.extension_proof,
            expected_previous_ledger_head_sha256=expected_previous_publication_sha256,
            expected_current_ledger_head_sha256=expected_current_publication_sha256,
        ):
            return False
        expected = canonical_json_sha256(_payload(packet))
        return hmac.compare_digest(expected, packet.attestation_sha256)
    except (CanonicalJSONError, TypeError, ValueError):
        return False
