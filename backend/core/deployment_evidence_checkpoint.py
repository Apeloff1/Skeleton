"""Unified externally pinnable checkpoint for deployment evidence.

Portable deployment proofs historically require three independent heads:
authorization journal, release channel, and transition receipts. This module binds
those heads into one deterministic checkpoint while retaining every channel head for
selective verification. Version 2 also binds exact authorization/receipt event counts,
which lets a publication ledger distinguish legitimate head advancement from stale
or equivocated heads under concurrent writers.

The checkpoint is an attestation, not a replacement for the underlying chain proofs;
external consumers still need to pin its root out of band.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hmac
import re
from typing import Any, Mapping

from core.canonical_json import CanonicalJSONError, canonical_json_sha256
from core.deployment_proof import PortableDeploymentProof, verify_portable_deployment_proof

DEPLOYMENT_EVIDENCE_CHECKPOINT_VERSION = 2
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ReleaseChannelCheckpoint:
    target: str
    environment: str
    releases: int
    head_sha256: str


@dataclass(frozen=True, slots=True)
class DeploymentEvidenceCheckpoint:
    version: int
    authorization_head_sha256: str
    authorization_events: int
    receipt_head_sha256: str
    receipt_events: int
    release_channels: tuple[ReleaseChannelCheckpoint, ...]
    completed_releases: int
    fully_portable_releases: int
    evidence_gap_count: int
    release_channels_sha256: str
    root_sha256: str
    attestation_sha256: str


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _payload(checkpoint: DeploymentEvidenceCheckpoint, *, include_root: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": checkpoint.version,
        "authorization_head_sha256": checkpoint.authorization_head_sha256,
        "authorization_events": checkpoint.authorization_events,
        "receipt_head_sha256": checkpoint.receipt_head_sha256,
        "receipt_events": checkpoint.receipt_events,
        "release_channels": [asdict(item) for item in checkpoint.release_channels],
        "completed_releases": checkpoint.completed_releases,
        "fully_portable_releases": checkpoint.fully_portable_releases,
        "evidence_gap_count": checkpoint.evidence_gap_count,
        "release_channels_sha256": checkpoint.release_channels_sha256,
    }
    if include_root:
        payload["root_sha256"] = checkpoint.root_sha256
    return payload


def _exact_nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _status_count(status: Mapping[str, Any], key: str) -> int:
    value = status.get(key)
    if not _exact_nonnegative_int(value):
        raise ValueError(f"deployment evidence status {key} must be a non-negative integer")
    return value


def _channel_rows(gateway) -> tuple[ReleaseChannelCheckpoint, ...]:
    grouped: dict[tuple[str, str], list[Any]] = {}
    for release in gateway.releases.snapshot():
        if not isinstance(release.target, str) or not release.target or release.target != release.target.strip():
            raise ValueError("release target is noncanonical")
        if not isinstance(release.environment, str) or not release.environment or release.environment != release.environment.strip():
            raise ValueError("release environment is noncanonical")
        if not _is_sha(release.sha256):
            raise ValueError("release head is malformed")
        grouped.setdefault((release.environment, release.target), []).append(release)
    rows: list[ReleaseChannelCheckpoint] = []
    for (environment, target), releases in sorted(grouped.items()):
        releases.sort(key=lambda row: row.sequence)
        rows.append(ReleaseChannelCheckpoint(
            target=target,
            environment=environment,
            releases=len(releases),
            head_sha256=releases[-1].sha256,
        ))
    return tuple(rows)


def build_deployment_evidence_checkpoint(gateway) -> DeploymentEvidenceCheckpoint:
    authorization = gateway.authorizations.status()
    receipts = gateway.receipts.status()
    portability = gateway.portability_status()
    gaps = gateway.evidence_gaps()
    if not isinstance(authorization, Mapping) or authorization.get("verified") is not True:
        raise ValueError("authorization ledger is not verified")
    if not isinstance(receipts, Mapping) or receipts.get("verified") is not True:
        raise ValueError("deployment receipt ledger is not verified")
    if not isinstance(portability, Mapping):
        raise ValueError("deployment portability status is malformed")
    if not isinstance(gaps, list):
        raise ValueError("deployment evidence gaps must be a list")
    channels = _channel_rows(gateway)

    authorization_head = authorization.get("head_sha256")
    receipt_head = receipts.get("head_sha256")
    if authorization_head and not _is_sha(authorization_head):
        raise ValueError("authorization head is malformed")
    if receipt_head and not _is_sha(receipt_head):
        raise ValueError("receipt head is malformed")
    # Empty ledgers are represented by hashes of explicit empty-domain markers,
    # never ambiguous blank roots.
    authorization_head = authorization_head or canonical_json_sha256({"ledger": "authorization", "empty": True})
    receipt_head = receipt_head or canonical_json_sha256({"ledger": "receipt", "empty": True})

    issued = _status_count(authorization, "issued")
    consumed = _status_count(authorization, "consumed")
    authorization_events = issued + consumed
    receipt_events = _status_count(receipts, "receipts")
    completed = _status_count(portability, "completed_releases")
    fully_portable = _status_count(portability, "fully_portable")
    if fully_portable > completed:
        raise ValueError("fully portable release count exceeds completed releases")
    channel_payload = [asdict(item) for item in channels]
    channels_sha = canonical_json_sha256(channel_payload)
    draft = DeploymentEvidenceCheckpoint(
        version=DEPLOYMENT_EVIDENCE_CHECKPOINT_VERSION,
        authorization_head_sha256=authorization_head,
        authorization_events=authorization_events,
        receipt_head_sha256=receipt_head,
        receipt_events=receipt_events,
        release_channels=channels,
        completed_releases=completed,
        fully_portable_releases=fully_portable,
        evidence_gap_count=len(gaps),
        release_channels_sha256=channels_sha,
        root_sha256="",
        attestation_sha256="",
    )
    root = canonical_json_sha256(_payload(draft, include_root=False))
    attestation = canonical_json_sha256({**_payload(draft, include_root=False), "root_sha256": root})
    return DeploymentEvidenceCheckpoint(
        version=draft.version,
        authorization_head_sha256=draft.authorization_head_sha256,
        authorization_events=draft.authorization_events,
        receipt_head_sha256=draft.receipt_head_sha256,
        receipt_events=draft.receipt_events,
        release_channels=draft.release_channels,
        completed_releases=draft.completed_releases,
        fully_portable_releases=draft.fully_portable_releases,
        evidence_gap_count=draft.evidence_gap_count,
        release_channels_sha256=draft.release_channels_sha256,
        root_sha256=root,
        attestation_sha256=attestation,
    )


def verify_deployment_evidence_checkpoint(checkpoint: DeploymentEvidenceCheckpoint) -> bool:
    try:
        if not isinstance(checkpoint, DeploymentEvidenceCheckpoint):
            return False
        if type(checkpoint.version) is not int or checkpoint.version != DEPLOYMENT_EVIDENCE_CHECKPOINT_VERSION:
            return False
        if not all(_is_sha(value) for value in (
            checkpoint.authorization_head_sha256,
            checkpoint.receipt_head_sha256,
            checkpoint.release_channels_sha256,
            checkpoint.root_sha256,
            checkpoint.attestation_sha256,
        )):
            return False
        if not all(_exact_nonnegative_int(value) for value in (
            checkpoint.authorization_events,
            checkpoint.receipt_events,
            checkpoint.completed_releases,
            checkpoint.fully_portable_releases,
            checkpoint.evidence_gap_count,
        )):
            return False
        if checkpoint.fully_portable_releases > checkpoint.completed_releases:
            return False
        if not isinstance(checkpoint.release_channels, tuple):
            return False
        seen: set[tuple[str, str]] = set()
        release_total = 0
        for row in checkpoint.release_channels:
            if not isinstance(row, ReleaseChannelCheckpoint):
                return False
            if not isinstance(row.target, str) or not row.target or row.target != row.target.strip():
                return False
            if not isinstance(row.environment, str) or not row.environment or row.environment != row.environment.strip():
                return False
            if type(row.releases) is not int or row.releases < 1 or not _is_sha(row.head_sha256):
                return False
            key = (row.environment, row.target)
            if key in seen:
                return False
            seen.add(key)
            release_total += row.releases
        if release_total != checkpoint.completed_releases:
            return False
        channel_payload = [asdict(item) for item in checkpoint.release_channels]
        if not hmac.compare_digest(canonical_json_sha256(channel_payload), checkpoint.release_channels_sha256):
            return False
        expected_root = canonical_json_sha256(_payload(checkpoint, include_root=False))
        if not hmac.compare_digest(expected_root, checkpoint.root_sha256):
            return False
        expected_attestation = canonical_json_sha256({
            **_payload(checkpoint, include_root=False),
            "root_sha256": checkpoint.root_sha256,
        })
        return hmac.compare_digest(expected_attestation, checkpoint.attestation_sha256)
    except (CanonicalJSONError, TypeError, ValueError):
        return False


def _proof_release_identity(proof: PortableDeploymentProof | Mapping[str, Any]) -> tuple[str, str] | None:
    try:
        raw = asdict(proof) if isinstance(proof, PortableDeploymentProof) else dict(proof)
    except (TypeError, ValueError):
        return None
    release = raw.get("release")
    if not isinstance(release, Mapping):
        return None
    target = release.get("target")
    environment = release.get("environment")
    if not isinstance(target, str) or not target or target != target.strip():
        return None
    if not isinstance(environment, str) or not environment or environment != environment.strip():
        return None
    return target, environment


def verify_deployment_proof_against_checkpoint(
    proof: PortableDeploymentProof | Mapping[str, Any],
    checkpoint: DeploymentEvidenceCheckpoint,
    *,
    expected_checkpoint_root_sha256: str,
) -> bool:
    """Verify a deployment proof using one externally pinned checkpoint root."""
    try:
        if not verify_deployment_evidence_checkpoint(checkpoint):
            return False
        if not _is_sha(expected_checkpoint_root_sha256):
            return False
        if not hmac.compare_digest(checkpoint.root_sha256, expected_checkpoint_root_sha256):
            return False
        identity = _proof_release_identity(proof)
        if identity is None:
            return False
        target, environment = identity
        channel = next((row for row in checkpoint.release_channels
                        if row.target == target and row.environment == environment), None)
        if channel is None:
            return False
        # A checkpoint reporting evidence gaps is still cryptographically verifiable,
        # but it is not suitable as deployment-proof authority.
        if checkpoint.evidence_gap_count != 0:
            return False
        return verify_portable_deployment_proof(
            proof,
            expected_authorization_head_sha256=checkpoint.authorization_head_sha256,
            expected_release_channel_head_sha256=channel.head_sha256,
            expected_receipt_head_sha256=checkpoint.receipt_head_sha256,
        )
    except (CanonicalJSONError, KeyError, TypeError, ValueError):
        return False
