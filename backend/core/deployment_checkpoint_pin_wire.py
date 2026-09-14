"""Strict wire decoder for externally submitted deployment checkpoint pin receipts."""
from __future__ import annotations

from dataclasses import fields
from typing import Any, Mapping

from core.canonical_json import CanonicalJSONError, canonical_json_clone
from core.deployment_checkpoint_ledger import DeploymentCheckpointLedgerError, _restore_publication
from core.deployment_checkpoint_witness import (
    DEPLOYMENT_CHECKPOINT_PIN_VERSION,
    DeploymentCheckpointPinReceipt,
)
from core.signed_transparency_witness import SignedWitnessStatement

_RECEIPT_KEYS = {"version", "publication", "witness", "receipt_sha256"}
_WITNESS_KEYS = {field.name for field in fields(SignedWitnessStatement)}


def decode_deployment_checkpoint_pin_receipt(raw: Any) -> DeploymentCheckpointPinReceipt:
    if not isinstance(raw, Mapping) or set(raw) != _RECEIPT_KEYS:
        raise ValueError("checkpoint pin receipt schema mismatch")
    version = raw.get("version")
    if type(version) is not int or version != DEPLOYMENT_CHECKPOINT_PIN_VERSION:
        raise ValueError("checkpoint pin receipt version malformed")
    witness_raw = raw.get("witness")
    if not isinstance(witness_raw, Mapping) or set(witness_raw) != _WITNESS_KEYS:
        raise ValueError("checkpoint pin witness schema mismatch")
    digest = raw.get("receipt_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("checkpoint pin receipt digest malformed")
    try:
        publication = _restore_publication(canonical_json_clone(raw.get("publication")))
        witness = SignedWitnessStatement(**canonical_json_clone(dict(witness_raw)))
    except (CanonicalJSONError, DeploymentCheckpointLedgerError, TypeError, ValueError) as exc:
        raise ValueError("checkpoint pin receipt is not portable canonical JSON") from exc
    return DeploymentCheckpointPinReceipt(version, publication, witness, digest)
