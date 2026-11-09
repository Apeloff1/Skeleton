"""Portable trust-policy rotation for deployment checkpoint witnesses.

A pinned policy digest cannot safely jump to a new digest without a bridge. Rotation
therefore requires two independently verified quorums over the same transition target:

* the old policy quorum authorizes leaving the currently pinned trust root;
* the new policy quorum proves possession of the replacement witness keys.

The verifier derives quorum and freshness from each manifest, verifies both witness
registries against their manifest fingerprints, and rejects security weakening by
default. The server never needs witness private keys; signing helpers exist for
external witness tooling and tests only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import base64
import hmac
from typing import Any, Iterable, Mapping

from core.canonical_json import CanonicalJSONError, canonical_json_clone, canonical_json_sha256
from core.deployment_checkpoint_trust_policy import (
    DeploymentCheckpointTrustPolicyManifest,
    decode_deployment_checkpoint_trust_policy_manifest,
    verify_deployment_checkpoint_trust_policy_manifest,
    verify_deployment_checkpoint_trust_registry,
)
from core.signed_transparency_witness import (
    SIGNED_WITNESS_VERSION,
    SignedWitnessStatement,
    sign_statement_for_witness,
    verify_signed_statement,
)
from core.transparency_witness import TrustedWitness

DEPLOYMENT_CHECKPOINT_POLICY_ROTATION_VERSION = 1
_ROTATION_DOMAIN = "skeleton.deployment.checkpoint-policy-rotation.v1"
_ROTATION_OLD_LOG_ID = "skeleton.deployment.checkpoint-policy-rotation.old.v1"
_ROTATION_NEW_LOG_ID = "skeleton.deployment.checkpoint-policy-rotation.new.v1"
_ROTATION_KEYS = {
    "version",
    "old_manifest",
    "new_manifest",
    "transition_sha256",
    "old_approvals",
    "new_approvals",
    "rotation_sha256",
}
_STATEMENT_KEYS = {
    "version",
    "log_id",
    "tree_size",
    "root_sha256",
    "witness_id",
    "independence_group",
    "observed_at",
    "nonce",
    "public_key_fingerprint",
    "signature_b64",
    "statement_sha256",
}


@dataclass(frozen=True, slots=True)
class DeploymentCheckpointPolicyRotation:
    version: int
    old_manifest: DeploymentCheckpointTrustPolicyManifest
    new_manifest: DeploymentCheckpointTrustPolicyManifest
    transition_sha256: str
    old_approvals: tuple[SignedWitnessStatement, ...]
    new_approvals: tuple[SignedWitnessStatement, ...]
    rotation_sha256: str


def _is_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("policy rotation timestamp must be canonical text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("policy rotation timestamp is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("policy rotation timestamp must be timezone-aware")
    normalized = parsed.astimezone(UTC).isoformat()
    if value.replace("Z", "+00:00") != normalized:
        raise ValueError("policy rotation timestamp must be normalized to UTC")
    return parsed.astimezone(UTC)


def _transition_payload(
    old_manifest_sha256: str,
    new_manifest_sha256: str,
) -> dict[str, Any]:
    if not _is_sha(old_manifest_sha256) or not _is_sha(new_manifest_sha256):
        raise ValueError("policy rotation manifest digests must be lowercase sha256")
    if hmac.compare_digest(old_manifest_sha256, new_manifest_sha256):
        raise ValueError("policy rotation requires a changed manifest identity")
    return {
        "domain": _ROTATION_DOMAIN,
        "version": DEPLOYMENT_CHECKPOINT_POLICY_ROTATION_VERSION,
        "old_manifest_sha256": old_manifest_sha256,
        "new_manifest_sha256": new_manifest_sha256,
    }


def deployment_checkpoint_policy_rotation_target(
    old_manifest: DeploymentCheckpointTrustPolicyManifest,
    new_manifest: DeploymentCheckpointTrustPolicyManifest,
) -> str:
    if not verify_deployment_checkpoint_trust_policy_manifest(
        old_manifest,
        expected_manifest_sha256=old_manifest.manifest_sha256,
    ):
        raise ValueError("old deployment checkpoint trust policy manifest is invalid")
    if not verify_deployment_checkpoint_trust_policy_manifest(
        new_manifest,
        expected_manifest_sha256=new_manifest.manifest_sha256,
    ):
        raise ValueError("new deployment checkpoint trust policy manifest is invalid")
    return canonical_json_sha256(
        _transition_payload(old_manifest.manifest_sha256, new_manifest.manifest_sha256)
    )


def sign_deployment_checkpoint_policy_rotation_approval(
    *,
    role: str,
    old_manifest: DeploymentCheckpointTrustPolicyManifest,
    new_manifest: DeploymentCheckpointTrustPolicyManifest,
    private_key_b64: str,
    public_key_b64: str,
    witness_id: str,
    independence_group: str,
    observed_at: str,
    nonce: str,
) -> SignedWitnessStatement:
    if role not in {"old", "new"}:
        raise ValueError("policy rotation approval role must be old or new")
    target = deployment_checkpoint_policy_rotation_target(old_manifest, new_manifest)
    return sign_statement_for_witness(
        private_key_b64=private_key_b64,
        public_key_b64=public_key_b64,
        log_id=_ROTATION_OLD_LOG_ID if role == "old" else _ROTATION_NEW_LOG_ID,
        tree_size=1,
        root_sha256=target,
        witness_id=witness_id,
        independence_group=independence_group,
        observed_at=observed_at,
        nonce=nonce,
    )


def _approval_shape(
    statement: SignedWitnessStatement,
    *,
    log_id: str,
    transition_sha256: str,
) -> bool:
    return (
        isinstance(statement, SignedWitnessStatement)
        and type(statement.version) is int
        and statement.version == SIGNED_WITNESS_VERSION
        and statement.log_id == log_id
        and type(statement.tree_size) is int
        and statement.tree_size == 1
        and hmac.compare_digest(statement.root_sha256, transition_sha256)
    )


def _normalize_approvals(
    approvals: Iterable[SignedWitnessStatement],
    *,
    log_id: str,
    transition_sha256: str,
) -> tuple[SignedWitnessStatement, ...]:
    rows = tuple(approvals)
    if not rows:
        raise ValueError("policy rotation requires witness approvals")
    if not all(
        _approval_shape(row, log_id=log_id, transition_sha256=transition_sha256)
        for row in rows
    ):
        raise ValueError("policy rotation approval target mismatch")
    ordered = tuple(sorted(rows, key=lambda row: row.witness_id))
    witness_ids = [row.witness_id for row in ordered]
    if len(witness_ids) != len(set(witness_ids)):
        raise ValueError("policy rotation contains duplicate witness approval")
    return ordered


def _payload(rotation: DeploymentCheckpointPolicyRotation) -> dict[str, Any]:
    return {
        "version": rotation.version,
        "old_manifest": asdict(rotation.old_manifest),
        "new_manifest": asdict(rotation.new_manifest),
        "transition_sha256": rotation.transition_sha256,
        "old_approvals": [asdict(row) for row in rotation.old_approvals],
        "new_approvals": [asdict(row) for row in rotation.new_approvals],
    }


def build_deployment_checkpoint_policy_rotation(
    *,
    old_manifest: DeploymentCheckpointTrustPolicyManifest,
    new_manifest: DeploymentCheckpointTrustPolicyManifest,
    old_approvals: Iterable[SignedWitnessStatement],
    new_approvals: Iterable[SignedWitnessStatement],
) -> DeploymentCheckpointPolicyRotation:
    transition = deployment_checkpoint_policy_rotation_target(old_manifest, new_manifest)
    old_rows = _normalize_approvals(
        old_approvals,
        log_id=_ROTATION_OLD_LOG_ID,
        transition_sha256=transition,
    )
    new_rows = _normalize_approvals(
        new_approvals,
        log_id=_ROTATION_NEW_LOG_ID,
        transition_sha256=transition,
    )
    draft = DeploymentCheckpointPolicyRotation(
        DEPLOYMENT_CHECKPOINT_POLICY_ROTATION_VERSION,
        old_manifest,
        new_manifest,
        transition,
        old_rows,
        new_rows,
        "",
    )
    digest = canonical_json_sha256(_payload(draft))
    return DeploymentCheckpointPolicyRotation(
        draft.version,
        draft.old_manifest,
        draft.new_manifest,
        draft.transition_sha256,
        draft.old_approvals,
        draft.new_approvals,
        digest,
    )


def deployment_checkpoint_policy_rotation_weakens_security(
    old_manifest: DeploymentCheckpointTrustPolicyManifest,
    new_manifest: DeploymentCheckpointTrustPolicyManifest,
) -> bool:
    return (
        (old_manifest.required and not new_manifest.required)
        or (old_manifest.continuity_required and not new_manifest.continuity_required)
        or new_manifest.required_groups < old_manifest.required_groups
        or new_manifest.max_age_seconds > old_manifest.max_age_seconds
    )


def _verify_approval_quorum(
    approvals: tuple[SignedWitnessStatement, ...],
    *,
    registry: tuple[TrustedWitness, ...],
    manifest: DeploymentCheckpointTrustPolicyManifest,
    log_id: str,
    transition_sha256: str,
    verified_at: str,
) -> bool:
    try:
        now = _parse_utc(verified_at)
        earliest = now - timedelta(seconds=manifest.max_age_seconds)
        by_id = {row.id: row for row in registry if row.enabled}
        seen: set[str] = set()
        groups: set[str] = set()
        for approval in approvals:
            if not _approval_shape(
                approval,
                log_id=log_id,
                transition_sha256=transition_sha256,
            ):
                return False
            if approval.witness_id in seen:
                return False
            seen.add(approval.witness_id)
            trusted = by_id.get(approval.witness_id)
            if trusted is None:
                return False
            observed = _parse_utc(approval.observed_at)
            if observed > now or observed < earliest:
                return False
            if not verify_signed_statement(
                approval,
                public_key_b64=trusted.public_key_b64,
                expected_group=trusted.independence_group,
            ):
                return False
            groups.add(trusted.independence_group)
        return len(groups) >= manifest.required_groups
    except (TypeError, ValueError):
        return False


def verify_deployment_checkpoint_policy_rotation(
    rotation: DeploymentCheckpointPolicyRotation,
    *,
    expected_old_manifest_sha256: str,
    old_trusted_witnesses: Iterable[TrustedWitness],
    new_trusted_witnesses: Iterable[TrustedWitness],
    verified_at: str,
    allow_policy_weakening: bool = False,
) -> bool:
    try:
        if not isinstance(rotation, DeploymentCheckpointPolicyRotation):
            return False
        if (
            type(rotation.version) is not int
            or rotation.version != DEPLOYMENT_CHECKPOINT_POLICY_ROTATION_VERSION
            or type(allow_policy_weakening) is not bool
        ):
            return False
        if not verify_deployment_checkpoint_trust_policy_manifest(
            rotation.old_manifest,
            expected_manifest_sha256=expected_old_manifest_sha256,
        ):
            return False
        if not verify_deployment_checkpoint_trust_policy_manifest(
            rotation.new_manifest,
            expected_manifest_sha256=rotation.new_manifest.manifest_sha256,
        ):
            return False
        old_registry = tuple(old_trusted_witnesses)
        new_registry = tuple(new_trusted_witnesses)
        if not verify_deployment_checkpoint_trust_registry(rotation.old_manifest, old_registry):
            return False
        if not verify_deployment_checkpoint_trust_registry(rotation.new_manifest, new_registry):
            return False
        transition = deployment_checkpoint_policy_rotation_target(
            rotation.old_manifest,
            rotation.new_manifest,
        )
        if not hmac.compare_digest(transition, rotation.transition_sha256):
            return False
        if (
            deployment_checkpoint_policy_rotation_weakens_security(
                rotation.old_manifest,
                rotation.new_manifest,
            )
            and not allow_policy_weakening
        ):
            return False
        if not _verify_approval_quorum(
            rotation.old_approvals,
            registry=old_registry,
            manifest=rotation.old_manifest,
            log_id=_ROTATION_OLD_LOG_ID,
            transition_sha256=transition,
            verified_at=verified_at,
        ):
            return False
        if not _verify_approval_quorum(
            rotation.new_approvals,
            registry=new_registry,
            manifest=rotation.new_manifest,
            log_id=_ROTATION_NEW_LOG_ID,
            transition_sha256=transition,
            verified_at=verified_at,
        ):
            return False
        if not _is_sha(rotation.rotation_sha256):
            return False
        expected = canonical_json_sha256(_payload(rotation))
        return hmac.compare_digest(expected, rotation.rotation_sha256)
    except (CanonicalJSONError, TypeError, ValueError):
        return False


def _decode_statement(raw: Any) -> SignedWitnessStatement:
    if not isinstance(raw, Mapping) or set(raw) != _STATEMENT_KEYS:
        raise ValueError("policy rotation witness approval schema mismatch")
    portable = canonical_json_clone(dict(raw))
    statement = SignedWitnessStatement(**portable)
    if type(statement.version) is not int or statement.version != SIGNED_WITNESS_VERSION:
        raise ValueError("policy rotation witness approval version malformed")
    if type(statement.tree_size) is not int or statement.tree_size != 1:
        raise ValueError("policy rotation witness approval tree size malformed")
    if not _is_sha(statement.root_sha256):
        raise ValueError("policy rotation witness approval root malformed")
    if not _is_sha(statement.public_key_fingerprint) or not _is_sha(statement.statement_sha256):
        raise ValueError("policy rotation witness approval digest malformed")
    if not all(
        isinstance(value, str) and value and value == value.strip()
        for value in (
            statement.log_id,
            statement.witness_id,
            statement.independence_group,
            statement.nonce,
        )
    ):
        raise ValueError("policy rotation witness approval text malformed")
    _parse_utc(statement.observed_at)
    try:
        signature = base64.b64decode(statement.signature_b64, validate=True)
    except Exception as exc:
        raise ValueError("policy rotation witness approval signature malformed") from exc
    if len(signature) != 64 or base64.b64encode(signature).decode("ascii") != statement.signature_b64:
        raise ValueError("policy rotation witness approval signature must be canonical Ed25519 base64")
    return statement


def decode_deployment_checkpoint_policy_rotation(raw: Any) -> DeploymentCheckpointPolicyRotation:
    if not isinstance(raw, Mapping) or set(raw) != _ROTATION_KEYS:
        raise ValueError("deployment checkpoint policy rotation schema mismatch")
    version = raw.get("version")
    if type(version) is not int or version != DEPLOYMENT_CHECKPOINT_POLICY_ROTATION_VERSION:
        raise ValueError("deployment checkpoint policy rotation version malformed")
    transition = raw.get("transition_sha256")
    digest = raw.get("rotation_sha256")
    if not _is_sha(transition) or not _is_sha(digest):
        raise ValueError("deployment checkpoint policy rotation digest malformed")
    old_manifest = decode_deployment_checkpoint_trust_policy_manifest(raw.get("old_manifest"))
    new_manifest = decode_deployment_checkpoint_trust_policy_manifest(raw.get("new_manifest"))
    old_raw = raw.get("old_approvals")
    new_raw = raw.get("new_approvals")
    if not isinstance(old_raw, list) or not isinstance(new_raw, list) or not old_raw or not new_raw:
        raise ValueError("deployment checkpoint policy rotation approvals must be non-empty JSON arrays")
    old_approvals = tuple(_decode_statement(row) for row in old_raw)
    new_approvals = tuple(_decode_statement(row) for row in new_raw)
    rotation = DeploymentCheckpointPolicyRotation(
        version,
        old_manifest,
        new_manifest,
        transition,
        old_approvals,
        new_approvals,
        digest,
    )
    expected_transition = deployment_checkpoint_policy_rotation_target(old_manifest, new_manifest)
    if not hmac.compare_digest(expected_transition, transition):
        raise ValueError("deployment checkpoint policy rotation target mismatch")
    if tuple(sorted(old_approvals, key=lambda row: row.witness_id)) != old_approvals:
        raise ValueError("deployment checkpoint old policy approvals must be sorted")
    if tuple(sorted(new_approvals, key=lambda row: row.witness_id)) != new_approvals:
        raise ValueError("deployment checkpoint new policy approvals must be sorted")
    expected = canonical_json_sha256(_payload(rotation))
    if not hmac.compare_digest(expected, digest):
        raise ValueError("deployment checkpoint policy rotation package integrity failed")
    return rotation
