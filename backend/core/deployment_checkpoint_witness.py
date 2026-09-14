"""Offline-verifiable witness pinning for deployment checkpoint publications.

A local append-only checkpoint ledger proves internal history. This module lets
independent external witnesses pin a specific publication head with Ed25519 and lets
an offline verifier require quorum across independently configured witness groups.

Trust roots are supplied by the verifier, never by the proof packet. Multiple
witnesses from one independence group count once. A signed pin authenticates
publication membership; it does not turn a checkpoint with evidence gaps into a
valid deployment authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import hmac
import re
from typing import Any, Iterable

from core.canonical_json import CanonicalJSONError, canonical_json_clone, canonical_json_sha256
from core.deployment_checkpoint_ledger import (
    DeploymentCheckpointPublication,
    DeploymentCheckpointLedgerError,
    _restore_publication,
)
from core.signed_transparency_witness import (
    SignedWitnessStatement,
    sign_statement_for_witness,
    verify_signed_statement,
)
from core.transparency_witness import TrustedWitness

DEPLOYMENT_CHECKPOINT_PIN_VERSION = 1
DEPLOYMENT_CHECKPOINT_LOG_ID = "skeleton.deployment.checkpoint-publications.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class DeploymentCheckpointPinReceipt:
    version: int
    publication: DeploymentCheckpointPublication
    witness: SignedWitnessStatement
    receipt_sha256: str


@dataclass(frozen=True, slots=True)
class DeploymentCheckpointPinBundle:
    version: int
    publication_sequence: int
    publication_sha256: str
    checkpoint_root_sha256: str
    required_groups: int
    receipts: tuple[DeploymentCheckpointPinReceipt, ...]
    bundle_sha256: str


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("witness pin timestamp must be canonical text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("witness pin timestamp must be timezone-aware")
    normalized = parsed.astimezone(UTC).isoformat()
    if value.replace("Z", "+00:00") != normalized:
        raise ValueError("witness pin timestamp must be normalized to UTC")
    return parsed.astimezone(UTC)


def _portable_publication(value: DeploymentCheckpointPublication) -> DeploymentCheckpointPublication:
    if not isinstance(value, DeploymentCheckpointPublication):
        raise ValueError("checkpoint publication type mismatch")
    portable = canonical_json_clone(asdict(value))
    restored = _restore_publication(portable)
    if restored != value:
        raise ValueError("checkpoint publication round-trip mismatch")
    return restored


def _receipt_payload(receipt: DeploymentCheckpointPinReceipt) -> dict[str, Any]:
    return {
        "version": receipt.version,
        "publication": asdict(receipt.publication),
        "witness": asdict(receipt.witness),
    }


def _bundle_payload(bundle: DeploymentCheckpointPinBundle) -> dict[str, Any]:
    return {
        "version": bundle.version,
        "publication_sequence": bundle.publication_sequence,
        "publication_sha256": bundle.publication_sha256,
        "checkpoint_root_sha256": bundle.checkpoint_root_sha256,
        "required_groups": bundle.required_groups,
        "receipts": [asdict(row) for row in bundle.receipts],
    }


def sign_deployment_checkpoint_pin(
    publication: DeploymentCheckpointPublication,
    *,
    private_key_b64: str,
    public_key_b64: str,
    witness_id: str,
    independence_group: str,
    observed_at: str,
    nonce: str,
) -> DeploymentCheckpointPinReceipt:
    publication = _portable_publication(publication)
    witness = sign_statement_for_witness(
        private_key_b64=private_key_b64,
        public_key_b64=public_key_b64,
        log_id=DEPLOYMENT_CHECKPOINT_LOG_ID,
        tree_size=publication.sequence,
        root_sha256=publication.sha256,
        witness_id=witness_id,
        independence_group=independence_group,
        observed_at=observed_at,
        nonce=nonce,
    )
    draft = DeploymentCheckpointPinReceipt(
        DEPLOYMENT_CHECKPOINT_PIN_VERSION,
        publication,
        witness,
        "",
    )
    digest = canonical_json_sha256(_receipt_payload(draft))
    return DeploymentCheckpointPinReceipt(draft.version, draft.publication, draft.witness, digest)


def verify_deployment_checkpoint_pin(
    receipt: DeploymentCheckpointPinReceipt,
    *,
    public_key_b64: str,
    expected_group: str,
    expected_publication_head_sha256: str | None = None,
) -> bool:
    try:
        if not isinstance(receipt, DeploymentCheckpointPinReceipt):
            return False
        if type(receipt.version) is not int or receipt.version != DEPLOYMENT_CHECKPOINT_PIN_VERSION:
            return False
        if not _is_sha(receipt.receipt_sha256):
            return False
        publication = _portable_publication(receipt.publication)
        witness = receipt.witness
        if witness.log_id != DEPLOYMENT_CHECKPOINT_LOG_ID:
            return False
        if type(witness.tree_size) is not int or witness.tree_size != publication.sequence:
            return False
        if not hmac.compare_digest(witness.root_sha256, publication.sha256):
            return False
        if expected_publication_head_sha256 is not None:
            if not _is_sha(expected_publication_head_sha256):
                return False
            if not hmac.compare_digest(publication.sha256, expected_publication_head_sha256):
                return False
        if not verify_signed_statement(witness, public_key_b64=public_key_b64, expected_group=expected_group):
            return False
        expected = canonical_json_sha256(_receipt_payload(receipt))
        return hmac.compare_digest(expected, receipt.receipt_sha256)
    except (CanonicalJSONError, DeploymentCheckpointLedgerError, TypeError, ValueError):
        return False


def build_deployment_checkpoint_pin_bundle(
    publication: DeploymentCheckpointPublication,
    receipts: Iterable[DeploymentCheckpointPinReceipt],
    *,
    required_groups: int,
) -> DeploymentCheckpointPinBundle:
    publication = _portable_publication(publication)
    if type(required_groups) is not int or required_groups < 1:
        raise ValueError("required_groups must be a positive integer")
    rows = tuple(receipts)
    if not rows:
        raise ValueError("checkpoint pin bundle requires at least one receipt")
    witness_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, DeploymentCheckpointPinReceipt):
            raise ValueError("checkpoint pin bundle contains invalid receipt type")
        if not hmac.compare_digest(row.publication.sha256, publication.sha256):
            raise ValueError("checkpoint pin receipt targets a different publication")
        if row.witness.witness_id in witness_ids:
            raise ValueError("checkpoint pin bundle contains duplicate witness identity")
        witness_ids.add(row.witness.witness_id)
    ordered = tuple(sorted(rows, key=lambda row: row.witness.witness_id))
    draft = DeploymentCheckpointPinBundle(
        version=DEPLOYMENT_CHECKPOINT_PIN_VERSION,
        publication_sequence=publication.sequence,
        publication_sha256=publication.sha256,
        checkpoint_root_sha256=publication.checkpoint_root_sha256,
        required_groups=required_groups,
        receipts=ordered,
        bundle_sha256="",
    )
    digest = canonical_json_sha256(_bundle_payload(draft))
    return DeploymentCheckpointPinBundle(
        draft.version,
        draft.publication_sequence,
        draft.publication_sha256,
        draft.checkpoint_root_sha256,
        draft.required_groups,
        draft.receipts,
        digest,
    )


def verify_deployment_checkpoint_pin_bundle(
    bundle: DeploymentCheckpointPinBundle,
    *,
    trusted_witnesses: Iterable[TrustedWitness],
    expected_publication_head_sha256: str,
    expected_required_groups: int,
    verified_at: str,
    max_age_seconds: int = 3600,
) -> bool:
    """Verify a signed checkpoint quorum against externally supplied trust policy."""
    try:
        if not isinstance(bundle, DeploymentCheckpointPinBundle):
            return False
        if type(bundle.version) is not int or bundle.version != DEPLOYMENT_CHECKPOINT_PIN_VERSION:
            return False
        if type(bundle.publication_sequence) is not int or bundle.publication_sequence < 1:
            return False
        if type(bundle.required_groups) is not int or bundle.required_groups < 1:
            return False
        if type(expected_required_groups) is not int or expected_required_groups < 1:
            return False
        if bundle.required_groups != expected_required_groups:
            return False
        if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 604800:
            return False
        if not all(_is_sha(value) for value in (
            bundle.publication_sha256,
            bundle.checkpoint_root_sha256,
            bundle.bundle_sha256,
            expected_publication_head_sha256,
        )):
            return False
        if not hmac.compare_digest(bundle.publication_sha256, expected_publication_head_sha256):
            return False
        if not isinstance(bundle.receipts, tuple) or not bundle.receipts:
            return False
        if tuple(sorted(bundle.receipts, key=lambda row: row.witness.witness_id)) != bundle.receipts:
            return False

        registry: dict[str, TrustedWitness] = {}
        for row in trusted_witnesses:
            if not isinstance(row, TrustedWitness) or type(row.enabled) is not bool:
                return False
            if not row.enabled:
                continue
            if not row.id or row.id in registry or not row.independence_group or not row.public_key_b64:
                return False
            registry[row.id] = row

        now = _parse_utc(verified_at)
        earliest = now - timedelta(seconds=max_age_seconds)
        witness_ids: set[str] = set()
        groups: set[str] = set()
        for receipt in bundle.receipts:
            witness_id = receipt.witness.witness_id
            if witness_id in witness_ids:
                return False
            witness_ids.add(witness_id)
            trusted = registry.get(witness_id)
            if trusted is None:
                return False
            if receipt.publication.sequence != bundle.publication_sequence:
                return False
            if not hmac.compare_digest(receipt.publication.sha256, bundle.publication_sha256):
                return False
            if not hmac.compare_digest(receipt.publication.checkpoint_root_sha256, bundle.checkpoint_root_sha256):
                return False
            observed = _parse_utc(receipt.witness.observed_at)
            if observed > now or observed < earliest:
                return False
            if not verify_deployment_checkpoint_pin(
                receipt,
                public_key_b64=trusted.public_key_b64,
                expected_group=trusted.independence_group,
                expected_publication_head_sha256=bundle.publication_sha256,
            ):
                return False
            groups.add(trusted.independence_group)

        if len(groups) < expected_required_groups:
            return False
        expected = canonical_json_sha256(_bundle_payload(bundle))
        return hmac.compare_digest(expected, bundle.bundle_sha256)
    except (CanonicalJSONError, DeploymentCheckpointLedgerError, TypeError, ValueError):
        return False
