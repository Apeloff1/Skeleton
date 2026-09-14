"""Portable identity for deployment-checkpoint witness policy.

A policy manifest is not self-authorizing. Its digest must be pinned out-of-band by an
auditor/operator. Once pinned, it detects silent changes to quorum, freshness,
continuity mode, witness identities/groups, or Ed25519 public keys without requiring
the verifier to trust policy values supplied by the server at verification time.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hmac
import re
from typing import Any, Iterable

from core.canonical_json import CanonicalJSONError, canonical_json_sha256
from core.deployment_checkpoint_pin_config import DeploymentCheckpointPinPolicy
from core.signed_transparency_witness import public_key_fingerprint
from core.transparency_witness import TrustedWitness

DEPLOYMENT_CHECKPOINT_TRUST_POLICY_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class DeploymentCheckpointTrustPolicyWitness:
    id: str
    independence_group: str
    public_key_fingerprint: str


@dataclass(frozen=True, slots=True)
class DeploymentCheckpointTrustPolicyManifest:
    version: int
    required_groups: int
    max_age_seconds: int
    required: bool
    continuity_required: bool
    witnesses: tuple[DeploymentCheckpointTrustPolicyWitness, ...]
    manifest_sha256: str


def _canonical_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be canonical non-empty text")
    return value


def _payload(manifest: DeploymentCheckpointTrustPolicyManifest) -> dict[str, Any]:
    return {
        "version": manifest.version,
        "required_groups": manifest.required_groups,
        "max_age_seconds": manifest.max_age_seconds,
        "required": manifest.required,
        "continuity_required": manifest.continuity_required,
        "witnesses": [asdict(row) for row in manifest.witnesses],
    }


def _manifest_witnesses(rows: Iterable[TrustedWitness]) -> tuple[DeploymentCheckpointTrustPolicyWitness, ...]:
    witnesses: list[DeploymentCheckpointTrustPolicyWitness] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, TrustedWitness):
            raise ValueError("deployment checkpoint trust registry contains unsupported entry")
        if type(row.enabled) is not bool:
            raise ValueError("deployment checkpoint trust witness enabled must be boolean")
        if not row.enabled:
            continue
        witness_id = _canonical_text(row.id, "deployment checkpoint trust witness id")
        group = _canonical_text(row.independence_group, "deployment checkpoint trust witness group")
        if witness_id in seen:
            raise ValueError(f"duplicate deployment checkpoint trust witness: {witness_id}")
        seen.add(witness_id)
        fingerprint = public_key_fingerprint(row.public_key_b64)
        witnesses.append(DeploymentCheckpointTrustPolicyWitness(witness_id, group, fingerprint))
    return tuple(sorted(witnesses, key=lambda row: row.id))


def build_deployment_checkpoint_trust_policy_manifest(
    policy: DeploymentCheckpointPinPolicy,
) -> DeploymentCheckpointTrustPolicyManifest:
    if not isinstance(policy, DeploymentCheckpointPinPolicy):
        raise ValueError("policy must be a DeploymentCheckpointPinPolicy")
    if type(policy.required_groups) is not int or not 1 <= policy.required_groups <= 64:
        raise ValueError("deployment checkpoint trust quorum malformed")
    if type(policy.max_age_seconds) is not int or not 1 <= policy.max_age_seconds <= 604800:
        raise ValueError("deployment checkpoint trust freshness malformed")
    if type(policy.required) is not bool or type(policy.continuity_required) is not bool:
        raise ValueError("deployment checkpoint trust requirement flags must be boolean")
    if policy.continuity_required and not policy.required:
        raise ValueError("deployment checkpoint trust continuity requires signed pins")
    witnesses = _manifest_witnesses(policy.witnesses)
    if policy.required and len({row.independence_group for row in witnesses}) < policy.required_groups:
        raise ValueError("deployment checkpoint trust policy cannot satisfy configured quorum")
    draft = DeploymentCheckpointTrustPolicyManifest(
        DEPLOYMENT_CHECKPOINT_TRUST_POLICY_VERSION,
        policy.required_groups,
        policy.max_age_seconds,
        policy.required,
        policy.continuity_required,
        witnesses,
        "",
    )
    digest = canonical_json_sha256(_payload(draft))
    return DeploymentCheckpointTrustPolicyManifest(
        draft.version,
        draft.required_groups,
        draft.max_age_seconds,
        draft.required,
        draft.continuity_required,
        draft.witnesses,
        digest,
    )


def verify_deployment_checkpoint_trust_policy_manifest(
    manifest: DeploymentCheckpointTrustPolicyManifest,
    *,
    expected_manifest_sha256: str,
) -> bool:
    try:
        if not isinstance(manifest, DeploymentCheckpointTrustPolicyManifest):
            return False
        if type(manifest.version) is not int or manifest.version != DEPLOYMENT_CHECKPOINT_TRUST_POLICY_VERSION:
            return False
        if type(manifest.required_groups) is not int or not 1 <= manifest.required_groups <= 64:
            return False
        if type(manifest.max_age_seconds) is not int or not 1 <= manifest.max_age_seconds <= 604800:
            return False
        if type(manifest.required) is not bool or type(manifest.continuity_required) is not bool:
            return False
        if manifest.continuity_required and not manifest.required:
            return False
        if not isinstance(expected_manifest_sha256, str) or not _SHA256.fullmatch(expected_manifest_sha256):
            return False
        if not isinstance(manifest.manifest_sha256, str) or not _SHA256.fullmatch(manifest.manifest_sha256):
            return False
        if tuple(sorted(manifest.witnesses, key=lambda row: row.id)) != manifest.witnesses:
            return False
        ids: set[str] = set()
        groups: set[str] = set()
        for row in manifest.witnesses:
            if not isinstance(row, DeploymentCheckpointTrustPolicyWitness):
                return False
            witness_id = _canonical_text(row.id, "witness id")
            group = _canonical_text(row.independence_group, "witness group")
            if witness_id in ids or not _SHA256.fullmatch(row.public_key_fingerprint):
                return False
            ids.add(witness_id)
            groups.add(group)
        if manifest.required and len(groups) < manifest.required_groups:
            return False
        expected = canonical_json_sha256(_payload(manifest))
        return (
            hmac.compare_digest(expected, manifest.manifest_sha256)
            and hmac.compare_digest(expected, expected_manifest_sha256)
        )
    except (CanonicalJSONError, TypeError, ValueError):
        return False


def verify_deployment_checkpoint_trust_registry(
    manifest: DeploymentCheckpointTrustPolicyManifest,
    trusted_witnesses: Iterable[TrustedWitness],
) -> bool:
    """Verify an externally supplied witness registry against a pinned manifest."""
    try:
        actual = _manifest_witnesses(trusted_witnesses)
        return actual == manifest.witnesses
    except (TypeError, ValueError):
        return False
