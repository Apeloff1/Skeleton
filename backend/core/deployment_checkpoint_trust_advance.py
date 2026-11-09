"""Portable trust advancement from a witnessed deployment checkpoint to a newer head.

The anchor is authenticated by an externally verifiable witness quorum. The suffix is
then verified as an append-only extension from that anchored publication to a newer
externally supplied current head. Trust keys, quorum policy, verification time, and the
new head are verifier inputs; none are allowed to self-authorize from the packet.
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

DEPLOYMENT_CHECKPOINT_TRUST_ADVANCE_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class DeploymentCheckpointTrustAdvance:
    version: int
    anchor_publication_sha256: str
    current_publication_sha256: str
    anchor_bundle: DeploymentCheckpointPinBundle
    extension_proof: DeploymentCheckpointPublicationProof
    attestation_sha256: str


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _payload(packet: DeploymentCheckpointTrustAdvance) -> dict[str, Any]:
    return {
        "version": packet.version,
        "anchor_publication_sha256": packet.anchor_publication_sha256,
        "current_publication_sha256": packet.current_publication_sha256,
        "anchor_bundle": asdict(packet.anchor_bundle),
        "extension_proof": asdict(packet.extension_proof),
    }


def build_deployment_checkpoint_trust_advance(*, pin_bundle: DeploymentCheckpointPinBundle,
                                              checkpoint_ledger) -> DeploymentCheckpointTrustAdvance:
    if not isinstance(pin_bundle, DeploymentCheckpointPinBundle):
        raise ValueError("pin_bundle must be a DeploymentCheckpointPinBundle")
    extension = build_deployment_checkpoint_publication_extension(
        checkpoint_ledger,
        pin_bundle.publication_sha256,
    )
    if not hmac.compare_digest(extension.publications[0].sha256, pin_bundle.publication_sha256):
        raise ValueError("checkpoint trust anchor diverges from extension proof")
    draft = DeploymentCheckpointTrustAdvance(
        version=DEPLOYMENT_CHECKPOINT_TRUST_ADVANCE_VERSION,
        anchor_publication_sha256=pin_bundle.publication_sha256,
        current_publication_sha256=extension.ledger_head_sha256,
        anchor_bundle=pin_bundle,
        extension_proof=extension,
        attestation_sha256="",
    )
    digest = canonical_json_sha256(_payload(draft))
    return DeploymentCheckpointTrustAdvance(
        draft.version,
        draft.anchor_publication_sha256,
        draft.current_publication_sha256,
        draft.anchor_bundle,
        draft.extension_proof,
        digest,
    )


def verify_deployment_checkpoint_trust_advance(
    packet: DeploymentCheckpointTrustAdvance,
    *,
    trusted_witnesses: Iterable[TrustedWitness],
    expected_required_groups: int,
    anchor_verified_at: str,
    expected_current_publication_sha256: str,
    witness_max_age_seconds: int = 3600,
) -> bool:
    try:
        if not isinstance(packet, DeploymentCheckpointTrustAdvance):
            return False
        if type(packet.version) is not int or packet.version != DEPLOYMENT_CHECKPOINT_TRUST_ADVANCE_VERSION:
            return False
        if not all(_is_sha(value) for value in (
            packet.anchor_publication_sha256,
            packet.current_publication_sha256,
            packet.attestation_sha256,
            expected_current_publication_sha256,
        )):
            return False
        if not hmac.compare_digest(packet.current_publication_sha256, expected_current_publication_sha256):
            return False
        if not hmac.compare_digest(packet.anchor_bundle.publication_sha256, packet.anchor_publication_sha256):
            return False
        if not packet.extension_proof.publications:
            return False
        if not hmac.compare_digest(packet.extension_proof.publications[0].sha256, packet.anchor_publication_sha256):
            return False
        if not verify_deployment_checkpoint_pin_bundle(
            packet.anchor_bundle,
            trusted_witnesses=trusted_witnesses,
            expected_publication_head_sha256=packet.anchor_publication_sha256,
            expected_required_groups=expected_required_groups,
            verified_at=anchor_verified_at,
            max_age_seconds=witness_max_age_seconds,
        ):
            return False
        if not verify_deployment_checkpoint_publication_extension(
            packet.extension_proof,
            expected_previous_ledger_head_sha256=packet.anchor_publication_sha256,
            expected_current_ledger_head_sha256=expected_current_publication_sha256,
        ):
            return False
        expected = canonical_json_sha256(_payload(packet))
        return hmac.compare_digest(expected, packet.attestation_sha256)
    except (CanonicalJSONError, TypeError, ValueError):
        return False
