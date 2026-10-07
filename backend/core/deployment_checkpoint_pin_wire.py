"""Strict wire decoder for externally submitted deployment checkpoint pin receipts.

Decoding is deliberately stronger than dataclass construction: exact schemas, exact
JSON scalar types, canonical timestamps/text/SHA fields, and canonical Ed25519
signature encoding are enforced before a receipt reaches the trusted-key verifier.
"""
from __future__ import annotations

import base64
from dataclasses import fields
from typing import Any, Mapping

from core.canonical_json import CanonicalJSONError, canonical_json_clone
from core.deployment_checkpoint_ledger import DeploymentCheckpointLedgerError, _restore_publication
from core.deployment_checkpoint_witness import (
    DEPLOYMENT_CHECKPOINT_PIN_VERSION,
    DeploymentCheckpointPinReceipt,
)
from core.signed_transparency_witness import (
    SIGNED_WITNESS_VERSION,
    SignedWitnessStatement,
    signed_payload,
)

_RECEIPT_KEYS = {"version", "publication", "witness", "receipt_sha256"}
_WITNESS_KEYS = {field.name for field in fields(SignedWitnessStatement)}


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{field} malformed")
    return value


def _canonical_signature(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("checkpoint pin witness signature malformed")
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise ValueError("checkpoint pin witness signature malformed") from exc
    if len(raw) != 64 or base64.b64encode(raw).decode("ascii") != value:
        raise ValueError("checkpoint pin witness signature malformed")
    return value


def _restore_witness(raw: Mapping[str, Any]) -> SignedWitnessStatement:
    version = raw.get("version")
    if type(version) is not int or version != SIGNED_WITNESS_VERSION:
        raise ValueError("checkpoint pin witness version malformed")
    fingerprint = _sha256(raw.get("public_key_fingerprint"), "checkpoint pin witness fingerprint")
    statement_sha = _sha256(raw.get("statement_sha256"), "checkpoint pin witness statement digest")
    signature = _canonical_signature(raw.get("signature_b64"))

    # signed_payload is the canonical validator used by the Ed25519 verifier itself.
    # It rejects bool-as-int tree sizes, noncanonical text, malformed roots, and
    # non-normalized/non-timezone-aware timestamps before any trust decision.
    payload = signed_payload(
        log_id=raw.get("log_id"),
        tree_size=raw.get("tree_size"),
        root_sha256=raw.get("root_sha256"),
        witness_id=raw.get("witness_id"),
        independence_group=raw.get("independence_group"),
        observed_at=raw.get("observed_at"),
        nonce=raw.get("nonce"),
        public_key_fingerprint=fingerprint,
    )
    return SignedWitnessStatement(
        version=version,
        log_id=payload["log_id"],
        tree_size=payload["tree_size"],
        root_sha256=payload["root_sha256"],
        witness_id=payload["witness_id"],
        independence_group=payload["independence_group"],
        observed_at=payload["observed_at"],
        nonce=payload["nonce"],
        public_key_fingerprint=fingerprint,
        signature_b64=signature,
        statement_sha256=statement_sha,
    )


def decode_deployment_checkpoint_pin_receipt(raw: Any) -> DeploymentCheckpointPinReceipt:
    if not isinstance(raw, Mapping) or set(raw) != _RECEIPT_KEYS:
        raise ValueError("checkpoint pin receipt schema mismatch")
    version = raw.get("version")
    if type(version) is not int or version != DEPLOYMENT_CHECKPOINT_PIN_VERSION:
        raise ValueError("checkpoint pin receipt version malformed")
    witness_raw = raw.get("witness")
    if not isinstance(witness_raw, Mapping) or set(witness_raw) != _WITNESS_KEYS:
        raise ValueError("checkpoint pin witness schema mismatch")
    digest = _sha256(raw.get("receipt_sha256"), "checkpoint pin receipt digest")
    try:
        publication = _restore_publication(canonical_json_clone(raw.get("publication")))
        witness_clone = canonical_json_clone(dict(witness_raw))
        witness = _restore_witness(witness_clone)
    except (CanonicalJSONError, DeploymentCheckpointLedgerError, TypeError, ValueError) as exc:
        raise ValueError("checkpoint pin receipt is not portable canonical JSON") from exc
    return DeploymentCheckpointPinReceipt(version, publication, witness, digest)
