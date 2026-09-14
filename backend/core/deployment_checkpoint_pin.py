"""Offline-verifiable Ed25519 pin receipts for deployment checkpoint heads.

A publication proof establishes membership in an append-only checkpoint journal. A pin
receipt adds an independent observer statement over a specific published head so an
auditor can retain compact external state and later request an append-only extension.
Trust keys are never carried as authority inside the receipt: verification requires the
observer public key supplied out-of-band.
"""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import re
from typing import Any, Mapping

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    InvalidSignature = Exception
    Ed25519PrivateKey = None
    Ed25519PublicKey = None
    _CRYPTO_AVAILABLE = False

from core.canonical_json import CanonicalJSONError, canonical_json_bytes, canonical_json_clone, canonical_json_sha256
from core.deployment_checkpoint_ledger import DeploymentCheckpointPublication

DEPLOYMENT_CHECKPOINT_PIN_VERSION = 1
_DOMAIN = "skeleton.deployment.checkpoint.pin.ed25519.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PIN_KEYS = {
    "version", "sequence", "checkpoint_root_sha256", "ledger_head_sha256",
    "observer_id", "independence_group", "observed_at", "nonce",
    "public_key_fingerprint", "signature_b64", "receipt_sha256",
}


@dataclass(frozen=True, slots=True)
class DeploymentCheckpointPinReceipt:
    version: int
    sequence: int
    checkpoint_root_sha256: str
    ledger_head_sha256: str
    observer_id: str
    independence_group: str
    observed_at: str
    nonce: str
    public_key_fingerprint: str
    signature_b64: str
    receipt_sha256: str


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be a canonical non-empty string")
    return value


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be lowercase sha256")
    return value


def _positive_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _utc(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("checkpoint pin timestamp must be a canonical non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("checkpoint pin timestamp is malformed") from exc
    if parsed.tzinfo is None:
        raise ValueError("checkpoint pin timestamp must be timezone-aware")
    normalized = parsed.astimezone(UTC).isoformat()
    if value.replace("Z", "+00:00") != normalized:
        raise ValueError("checkpoint pin timestamp must be normalized to UTC")
    return normalized


def _b64(value: Any, field: str, expected_len: int) -> bytes:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be canonical base64 text")
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise ValueError(f"{field} is invalid base64") from exc
    if len(raw) != expected_len or base64.b64encode(raw).decode("ascii") != value:
        raise ValueError(f"{field} must be canonical base64 for {expected_len} bytes")
    return raw


def public_key_fingerprint(public_key_b64: str) -> str:
    return hashlib.sha256(_b64(public_key_b64, "public_key_b64", 32)).hexdigest()


def _payload(*, sequence: int, checkpoint_root_sha256: str, ledger_head_sha256: str,
             observer_id: str, independence_group: str, observed_at: str, nonce: str,
             public_key_fingerprint: str) -> dict[str, Any]:
    return {
        "domain": _DOMAIN,
        "version": DEPLOYMENT_CHECKPOINT_PIN_VERSION,
        "sequence": _positive_int(sequence, "sequence"),
        "checkpoint_root_sha256": _sha(checkpoint_root_sha256, "checkpoint_root_sha256"),
        "ledger_head_sha256": _sha(ledger_head_sha256, "ledger_head_sha256"),
        "observer_id": _text(observer_id, "observer_id"),
        "independence_group": _text(independence_group, "independence_group"),
        "observed_at": _utc(observed_at),
        "nonce": _text(nonce, "nonce"),
        "public_key_fingerprint": _sha(public_key_fingerprint, "public_key_fingerprint"),
    }


def sign_checkpoint_pin(*, publication: DeploymentCheckpointPublication,
                        private_key_b64: str, public_key_b64: str,
                        observer_id: str, independence_group: str,
                        observed_at: str, nonce: str) -> DeploymentCheckpointPinReceipt:
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography is required for checkpoint pin signing")
    if not isinstance(publication, DeploymentCheckpointPublication):
        raise ValueError("publication type mismatch")
    private_bytes = _b64(private_key_b64, "private_key_b64", 32)
    public_bytes = _b64(public_key_b64, "public_key_b64", 32)
    private = Ed25519PrivateKey.from_private_bytes(private_bytes)
    if not hmac.compare_digest(private.public_key().public_bytes_raw(), public_bytes):
        raise ValueError("private/public observer key pair does not match")
    fingerprint = hashlib.sha256(public_bytes).hexdigest()
    payload = _payload(
        sequence=publication.sequence,
        checkpoint_root_sha256=publication.checkpoint_root_sha256,
        ledger_head_sha256=publication.sha256,
        observer_id=observer_id,
        independence_group=independence_group,
        observed_at=observed_at,
        nonce=nonce,
        public_key_fingerprint=fingerprint,
    )
    signature_b64 = base64.b64encode(private.sign(canonical_json_bytes(payload))).decode("ascii")
    receipt_sha256 = canonical_json_sha256({**payload, "signature_b64": signature_b64})
    return DeploymentCheckpointPinReceipt(
        version=DEPLOYMENT_CHECKPOINT_PIN_VERSION,
        sequence=payload["sequence"],
        checkpoint_root_sha256=payload["checkpoint_root_sha256"],
        ledger_head_sha256=payload["ledger_head_sha256"],
        observer_id=payload["observer_id"],
        independence_group=payload["independence_group"],
        observed_at=payload["observed_at"],
        nonce=payload["nonce"],
        public_key_fingerprint=fingerprint,
        signature_b64=signature_b64,
        receipt_sha256=receipt_sha256,
    )


def verify_checkpoint_pin(receipt: DeploymentCheckpointPinReceipt | Mapping[str, Any], *,
                          public_key_b64: str,
                          expected_observer_id: str | None = None,
                          expected_group: str | None = None,
                          expected_ledger_head_sha256: str | None = None,
                          expected_checkpoint_root_sha256: str | None = None) -> bool:
    if not _CRYPTO_AVAILABLE:
        return False
    try:
        raw = asdict(receipt) if isinstance(receipt, DeploymentCheckpointPinReceipt) else dict(receipt)
        if set(raw) != _PIN_KEYS:
            return False
        raw = canonical_json_clone(raw)
        if type(raw["version"]) is not int or raw["version"] != DEPLOYMENT_CHECKPOINT_PIN_VERSION:
            return False
        fingerprint = public_key_fingerprint(public_key_b64)
        if not hmac.compare_digest(_sha(raw["public_key_fingerprint"], "public_key_fingerprint"), fingerprint):
            return False
        payload = _payload(
            sequence=raw["sequence"],
            checkpoint_root_sha256=raw["checkpoint_root_sha256"],
            ledger_head_sha256=raw["ledger_head_sha256"],
            observer_id=raw["observer_id"],
            independence_group=raw["independence_group"],
            observed_at=raw["observed_at"],
            nonce=raw["nonce"],
            public_key_fingerprint=fingerprint,
        )
        if expected_observer_id is not None and payload["observer_id"] != _text(expected_observer_id, "expected_observer_id"):
            return False
        if expected_group is not None and payload["independence_group"] != _text(expected_group, "expected_group"):
            return False
        if expected_ledger_head_sha256 is not None and not hmac.compare_digest(payload["ledger_head_sha256"], _sha(expected_ledger_head_sha256, "expected_ledger_head_sha256")):
            return False
        if expected_checkpoint_root_sha256 is not None and not hmac.compare_digest(payload["checkpoint_root_sha256"], _sha(expected_checkpoint_root_sha256, "expected_checkpoint_root_sha256")):
            return False
        signature = _b64(raw["signature_b64"], "signature_b64", 64)
        public = Ed25519PublicKey.from_public_bytes(_b64(public_key_b64, "public_key_b64", 32))
        public.verify(signature, canonical_json_bytes(payload))
        expected_receipt = canonical_json_sha256({**payload, "signature_b64": raw["signature_b64"]})
        return hmac.compare_digest(expected_receipt, _sha(raw["receipt_sha256"], "receipt_sha256"))
    except (CanonicalJSONError, InvalidSignature, KeyError, TypeError, ValueError):
        return False
