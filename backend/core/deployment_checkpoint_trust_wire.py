"""Strict JSON-wire decoders for portable deployment checkpoint trust proofs.

These functions reconstruct proof dataclasses only after validating exact object keys,
exact scalar types, canonical SHA-256 fields, JSON-array containers, and every nested
publication/receipt. Cryptographic authority is still established only by the normal
verify functions with externally supplied trust roots and expected heads.
"""
from __future__ import annotations

from typing import Any, Mapping

from core.canonical_json import CanonicalJSONError, canonical_json_clone
from core.deployment_checkpoint_ledger import DeploymentCheckpointLedgerError, _restore_publication
from core.deployment_checkpoint_pin_wire import decode_deployment_checkpoint_pin_receipt
from core.deployment_checkpoint_proof import (
    DEPLOYMENT_CHECKPOINT_PROOF_VERSION,
    DeploymentCheckpointPublicationProof,
)
from core.deployment_checkpoint_trust_advance import (
    DEPLOYMENT_CHECKPOINT_TRUST_ADVANCE_VERSION,
    DeploymentCheckpointTrustAdvance,
)
from core.deployment_checkpoint_witness import (
    DEPLOYMENT_CHECKPOINT_PIN_VERSION,
    DeploymentCheckpointPinBundle,
)
from core.deployment_checkpoint_witnessed_continuity import (
    DEPLOYMENT_CHECKPOINT_WITNESSED_CONTINUITY_VERSION,
    DeploymentCheckpointWitnessedContinuity,
)

_BUNDLE_KEYS = {
    "version", "publication_sequence", "publication_sha256",
    "checkpoint_root_sha256", "required_groups", "receipts", "bundle_sha256",
}
_PROOF_KEYS = {
    "version", "start_sequence", "end_sequence", "start_checkpoint_root_sha256",
    "end_checkpoint_root_sha256", "ledger_head_sha256", "publications", "proof_sha256",
}
_ADVANCE_KEYS = {
    "version", "anchor_publication_sha256", "current_publication_sha256",
    "anchor_bundle", "extension_proof", "attestation_sha256",
}
_CONTINUITY_KEYS = {
    "version", "previous_publication_sha256", "current_publication_sha256",
    "previous_bundle", "current_bundle", "extension_proof", "attestation_sha256",
}


def _exact_object(raw: Any, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != keys:
        raise ValueError(f"{label} schema mismatch")
    return raw


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be lowercase sha256")
    return value


def decode_deployment_checkpoint_pin_bundle(raw: Any) -> DeploymentCheckpointPinBundle:
    raw = _exact_object(raw, _BUNDLE_KEYS, "checkpoint pin bundle")
    version = raw.get("version")
    if type(version) is not int or version != DEPLOYMENT_CHECKPOINT_PIN_VERSION:
        raise ValueError("checkpoint pin bundle version malformed")
    sequence = _positive_int(raw.get("publication_sequence"), "checkpoint pin publication sequence")
    required_groups = _positive_int(raw.get("required_groups"), "checkpoint pin required groups")
    publication_sha = _sha256(raw.get("publication_sha256"), "checkpoint pin publication digest")
    checkpoint_root = _sha256(raw.get("checkpoint_root_sha256"), "checkpoint pin checkpoint root")
    bundle_sha = _sha256(raw.get("bundle_sha256"), "checkpoint pin bundle digest")
    receipts_raw = raw.get("receipts")
    if not isinstance(receipts_raw, list) or not receipts_raw:
        raise ValueError("checkpoint pin bundle receipts must be a non-empty JSON array")
    receipts = tuple(decode_deployment_checkpoint_pin_receipt(row) for row in receipts_raw)
    witness_ids = [row.witness.witness_id for row in receipts]
    if witness_ids != sorted(witness_ids) or len(witness_ids) != len(set(witness_ids)):
        raise ValueError("checkpoint pin bundle witnesses must be unique and sorted")
    for receipt in receipts:
        if receipt.publication.sequence != sequence or receipt.publication.sha256 != publication_sha:
            raise ValueError("checkpoint pin bundle receipt target mismatch")
        if receipt.publication.checkpoint_root_sha256 != checkpoint_root:
            raise ValueError("checkpoint pin bundle receipt checkpoint mismatch")
    return DeploymentCheckpointPinBundle(
        version, sequence, publication_sha, checkpoint_root, required_groups, receipts, bundle_sha,
    )


def decode_deployment_checkpoint_publication_proof(raw: Any) -> DeploymentCheckpointPublicationProof:
    raw = _exact_object(raw, _PROOF_KEYS, "checkpoint publication proof")
    version = raw.get("version")
    if type(version) is not int or version != DEPLOYMENT_CHECKPOINT_PROOF_VERSION:
        raise ValueError("checkpoint publication proof version malformed")
    start = _positive_int(raw.get("start_sequence"), "checkpoint proof start sequence")
    end = _positive_int(raw.get("end_sequence"), "checkpoint proof end sequence")
    if end < start:
        raise ValueError("checkpoint proof end sequence precedes start")
    start_root = _sha256(raw.get("start_checkpoint_root_sha256"), "checkpoint proof start root")
    end_root = _sha256(raw.get("end_checkpoint_root_sha256"), "checkpoint proof end root")
    head = _sha256(raw.get("ledger_head_sha256"), "checkpoint proof ledger head")
    proof_sha = _sha256(raw.get("proof_sha256"), "checkpoint proof digest")
    publications_raw = raw.get("publications")
    if not isinstance(publications_raw, list) or not publications_raw:
        raise ValueError("checkpoint proof publications must be a non-empty JSON array")
    if len(publications_raw) != end - start + 1:
        raise ValueError("checkpoint proof publication cardinality mismatch")
    try:
        publications = tuple(
            _restore_publication(canonical_json_clone(row)) for row in publications_raw
        )
    except (CanonicalJSONError, DeploymentCheckpointLedgerError, TypeError, ValueError) as exc:
        raise ValueError("checkpoint proof contains a noncanonical publication") from exc
    if publications[0].sequence != start or publications[-1].sequence != end:
        raise ValueError("checkpoint proof publication sequence mismatch")
    if publications[0].checkpoint_root_sha256 != start_root:
        raise ValueError("checkpoint proof start root mismatch")
    if publications[-1].checkpoint_root_sha256 != end_root:
        raise ValueError("checkpoint proof end root mismatch")
    if publications[-1].sha256 != head:
        raise ValueError("checkpoint proof ledger head mismatch")
    return DeploymentCheckpointPublicationProof(
        version, start, end, start_root, end_root, head, publications, proof_sha,
    )


def decode_deployment_checkpoint_trust_advance(raw: Any) -> DeploymentCheckpointTrustAdvance:
    raw = _exact_object(raw, _ADVANCE_KEYS, "checkpoint trust advance")
    version = raw.get("version")
    if type(version) is not int or version != DEPLOYMENT_CHECKPOINT_TRUST_ADVANCE_VERSION:
        raise ValueError("checkpoint trust advance version malformed")
    anchor_sha = _sha256(raw.get("anchor_publication_sha256"), "checkpoint trust anchor")
    current_sha = _sha256(raw.get("current_publication_sha256"), "checkpoint trust current head")
    attestation = _sha256(raw.get("attestation_sha256"), "checkpoint trust advance attestation")
    anchor_bundle = decode_deployment_checkpoint_pin_bundle(raw.get("anchor_bundle"))
    proof = decode_deployment_checkpoint_publication_proof(raw.get("extension_proof"))
    if anchor_bundle.publication_sha256 != anchor_sha:
        raise ValueError("checkpoint trust anchor bundle mismatch")
    if proof.publications[0].sha256 != anchor_sha or proof.ledger_head_sha256 != current_sha:
        raise ValueError("checkpoint trust extension endpoints mismatch")
    return DeploymentCheckpointTrustAdvance(
        version, anchor_sha, current_sha, anchor_bundle, proof, attestation,
    )


def decode_deployment_checkpoint_witnessed_continuity(
    raw: Any,
) -> DeploymentCheckpointWitnessedContinuity:
    raw = _exact_object(raw, _CONTINUITY_KEYS, "checkpoint witnessed continuity")
    version = raw.get("version")
    if type(version) is not int or version != DEPLOYMENT_CHECKPOINT_WITNESSED_CONTINUITY_VERSION:
        raise ValueError("checkpoint witnessed continuity version malformed")
    previous_sha = _sha256(raw.get("previous_publication_sha256"), "checkpoint continuity previous head")
    current_sha = _sha256(raw.get("current_publication_sha256"), "checkpoint continuity current head")
    attestation = _sha256(raw.get("attestation_sha256"), "checkpoint continuity attestation")
    previous_bundle = decode_deployment_checkpoint_pin_bundle(raw.get("previous_bundle"))
    current_bundle = decode_deployment_checkpoint_pin_bundle(raw.get("current_bundle"))
    proof = decode_deployment_checkpoint_publication_proof(raw.get("extension_proof"))
    if previous_bundle.publication_sequence >= current_bundle.publication_sequence:
        raise ValueError("checkpoint continuity endpoint order invalid")
    if previous_bundle.publication_sha256 != previous_sha:
        raise ValueError("checkpoint continuity previous bundle mismatch")
    if current_bundle.publication_sha256 != current_sha:
        raise ValueError("checkpoint continuity current bundle mismatch")
    if proof.publications[0].sha256 != previous_sha or proof.ledger_head_sha256 != current_sha:
        raise ValueError("checkpoint continuity extension endpoints mismatch")
    return DeploymentCheckpointWitnessedContinuity(
        version, previous_sha, current_sha, previous_bundle, current_bundle, proof, attestation,
    )
