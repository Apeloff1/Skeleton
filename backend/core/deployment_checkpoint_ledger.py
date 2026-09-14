"""Append-only publication ledger for unified deployment-evidence checkpoints.

A deployment checkpoint is useful to an external verifier only after its root has
been anchored somewhere durable. This ledger provides that local anchoring primitive:
each publication embeds a fully self-verifying checkpoint, links to the prior
publication, uses strict canonical JSON, fsyncs before returning, and validates
monotonic release/channel evolution on every replay.

The ledger intentionally allows checkpoints that report evidence gaps. Recording an
incident is part of the forensic truth. Such a checkpoint remains unsuitable as proof
authority because ``verify_deployment_proof_against_checkpoint`` already fails closed
when ``evidence_gap_count`` is non-zero.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hmac
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from core.canonical_json import CanonicalJSONError, canonical_json_sha256, canonical_json_text
from core.deployment_evidence_checkpoint import (
    DEPLOYMENT_EVIDENCE_CHECKPOINT_VERSION,
    DeploymentEvidenceCheckpoint,
    ReleaseChannelCheckpoint,
    verify_deployment_evidence_checkpoint,
)
from core.file_lease import FileLease

DEPLOYMENT_CHECKPOINT_LEDGER_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PUBLICATION_KEYS = {
    "version",
    "sequence",
    "checkpoint",
    "checkpoint_root_sha256",
    "checkpoint_attestation_sha256",
    "published_at",
    "previous_checkpoint_root_sha256",
    "previous_sha256",
    "sha256",
}
_CHECKPOINT_KEYS = {
    "version",
    "authorization_head_sha256",
    "receipt_head_sha256",
    "release_channels",
    "completed_releases",
    "fully_portable_releases",
    "evidence_gap_count",
    "release_channels_sha256",
    "root_sha256",
    "attestation_sha256",
}
_CHANNEL_KEYS = {"target", "environment", "releases", "head_sha256"}


class DeploymentCheckpointLedgerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DeploymentCheckpointPublication:
    version: int
    sequence: int
    checkpoint: DeploymentEvidenceCheckpoint
    checkpoint_root_sha256: str
    checkpoint_attestation_sha256: str
    published_at: str
    previous_checkpoint_root_sha256: str
    previous_sha256: str
    sha256: str


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("checkpoint publication timestamp must be a canonical non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("checkpoint publication timestamp is malformed") from exc
    if parsed.tzinfo is None:
        raise ValueError("checkpoint publication timestamp must be timezone-aware")
    normalized = parsed.astimezone(UTC).isoformat()
    if value.replace("Z", "+00:00") != normalized:
        raise ValueError("checkpoint publication timestamp must be normalized to UTC")
    return parsed.astimezone(UTC)


def _checkpoint_from_mapping(raw: Any) -> DeploymentEvidenceCheckpoint:
    if not isinstance(raw, Mapping) or set(raw) != _CHECKPOINT_KEYS:
        raise ValueError("deployment checkpoint schema mismatch")
    channels_raw = raw.get("release_channels")
    if not isinstance(channels_raw, list):
        raise ValueError("deployment checkpoint channels must be a JSON array")
    channels: list[ReleaseChannelCheckpoint] = []
    for item in channels_raw:
        if not isinstance(item, Mapping) or set(item) != _CHANNEL_KEYS:
            raise ValueError("deployment checkpoint channel schema mismatch")
        channels.append(ReleaseChannelCheckpoint(
            target=item.get("target"),
            environment=item.get("environment"),
            releases=item.get("releases"),
            head_sha256=item.get("head_sha256"),
        ))
    checkpoint = DeploymentEvidenceCheckpoint(
        version=raw.get("version"),
        authorization_head_sha256=raw.get("authorization_head_sha256"),
        receipt_head_sha256=raw.get("receipt_head_sha256"),
        release_channels=tuple(channels),
        completed_releases=raw.get("completed_releases"),
        fully_portable_releases=raw.get("fully_portable_releases"),
        evidence_gap_count=raw.get("evidence_gap_count"),
        release_channels_sha256=raw.get("release_channels_sha256"),
        root_sha256=raw.get("root_sha256"),
        attestation_sha256=raw.get("attestation_sha256"),
    )
    if not verify_deployment_evidence_checkpoint(checkpoint):
        raise ValueError("deployment checkpoint failed verification")
    return checkpoint


def _publication_payload(publication: DeploymentCheckpointPublication) -> dict[str, Any]:
    raw = asdict(publication)
    raw.pop("sha256", None)
    return raw


def _channel_index(checkpoint: DeploymentEvidenceCheckpoint) -> dict[tuple[str, str], ReleaseChannelCheckpoint]:
    return {(row.environment, row.target): row for row in checkpoint.release_channels}


def _validate_evolution(previous: DeploymentEvidenceCheckpoint, current: DeploymentEvidenceCheckpoint) -> None:
    if current.completed_releases < previous.completed_releases:
        raise DeploymentCheckpointLedgerError("deployment checkpoint release count regressed")
    if current.fully_portable_releases < previous.fully_portable_releases:
        raise DeploymentCheckpointLedgerError("deployment checkpoint portable release count regressed")

    old_channels = _channel_index(previous)
    new_channels = _channel_index(current)
    missing = set(old_channels) - set(new_channels)
    if missing:
        raise DeploymentCheckpointLedgerError("deployment checkpoint removed an existing release channel")
    for key, old in old_channels.items():
        new = new_channels[key]
        if new.releases < old.releases:
            raise DeploymentCheckpointLedgerError("deployment checkpoint channel release count regressed")
        if new.releases == old.releases and not hmac.compare_digest(new.head_sha256, old.head_sha256):
            raise DeploymentCheckpointLedgerError("deployment checkpoint channel head changed without a release")
        if new.releases > old.releases and hmac.compare_digest(new.head_sha256, old.head_sha256):
            raise DeploymentCheckpointLedgerError("deployment checkpoint channel advanced without rotating its head")


def _restore_publication(raw: Any) -> DeploymentCheckpointPublication:
    if not isinstance(raw, Mapping) or set(raw) != _PUBLICATION_KEYS:
        raise DeploymentCheckpointLedgerError("checkpoint publication schema mismatch")
    if type(raw.get("version")) is not int or raw.get("version") != DEPLOYMENT_CHECKPOINT_LEDGER_VERSION:
        raise DeploymentCheckpointLedgerError("checkpoint publication version malformed")
    if type(raw.get("sequence")) is not int or raw["sequence"] < 1:
        raise DeploymentCheckpointLedgerError("checkpoint publication sequence malformed")
    for field in (
        "checkpoint_root_sha256",
        "checkpoint_attestation_sha256",
        "previous_checkpoint_root_sha256",
        "previous_sha256",
        "sha256",
    ):
        value = raw.get(field)
        if not isinstance(value, str):
            raise DeploymentCheckpointLedgerError(f"checkpoint publication {field} type mismatch")
    if not _is_sha(raw["checkpoint_root_sha256"]) or not _is_sha(raw["checkpoint_attestation_sha256"]):
        raise DeploymentCheckpointLedgerError("checkpoint publication checkpoint identity malformed")
    if raw["previous_checkpoint_root_sha256"] and not _is_sha(raw["previous_checkpoint_root_sha256"]):
        raise DeploymentCheckpointLedgerError("checkpoint publication previous checkpoint root malformed")
    if raw["previous_sha256"] and not _is_sha(raw["previous_sha256"]):
        raise DeploymentCheckpointLedgerError("checkpoint publication previous digest malformed")
    if not _is_sha(raw["sha256"]):
        raise DeploymentCheckpointLedgerError("checkpoint publication digest malformed")
    try:
        _parse_utc(raw.get("published_at"))
        checkpoint = _checkpoint_from_mapping(raw.get("checkpoint"))
    except ValueError as exc:
        raise DeploymentCheckpointLedgerError(str(exc)) from exc
    if not hmac.compare_digest(checkpoint.root_sha256, raw["checkpoint_root_sha256"]):
        raise DeploymentCheckpointLedgerError("checkpoint publication root diverges from embedded checkpoint")
    if not hmac.compare_digest(checkpoint.attestation_sha256, raw["checkpoint_attestation_sha256"]):
        raise DeploymentCheckpointLedgerError("checkpoint publication attestation diverges from embedded checkpoint")
    publication = DeploymentCheckpointPublication(
        version=raw["version"],
        sequence=raw["sequence"],
        checkpoint=checkpoint,
        checkpoint_root_sha256=raw["checkpoint_root_sha256"],
        checkpoint_attestation_sha256=raw["checkpoint_attestation_sha256"],
        published_at=raw["published_at"],
        previous_checkpoint_root_sha256=raw["previous_checkpoint_root_sha256"],
        previous_sha256=raw["previous_sha256"],
        sha256=raw["sha256"],
    )
    try:
        expected = canonical_json_sha256(_publication_payload(publication))
    except CanonicalJSONError as exc:
        raise DeploymentCheckpointLedgerError("checkpoint publication is not canonical JSON") from exc
    if not hmac.compare_digest(expected, publication.sha256):
        raise DeploymentCheckpointLedgerError("checkpoint publication hash mismatch")
    return publication


class DeploymentCheckpointLedger:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "deployment-checkpoints.jsonl"
        self._lease = FileLease(self.root / ".deployment-checkpoints.lock")
        with self._lease.acquire():
            if not self.path.exists():
                self.path.touch()
            self._load_verified()

    def _load_verified(self) -> tuple[DeploymentCheckpointPublication, ...]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise DeploymentCheckpointLedgerError("checkpoint publication ledger unreadable") from exc
        rows: list[DeploymentCheckpointPublication] = []
        roots: set[str] = set()
        previous_time: datetime | None = None
        for expected_sequence, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DeploymentCheckpointLedgerError("checkpoint publication ledger malformed") from exc
            row = _restore_publication(raw)
            if row.sequence != expected_sequence:
                raise DeploymentCheckpointLedgerError("checkpoint publication sequence mismatch")
            previous = rows[-1] if rows else None
            expected_previous_sha = previous.sha256 if previous else ""
            expected_previous_root = previous.checkpoint_root_sha256 if previous else ""
            if row.previous_sha256 != expected_previous_sha:
                raise DeploymentCheckpointLedgerError("checkpoint publication ancestry mismatch")
            if row.previous_checkpoint_root_sha256 != expected_previous_root:
                raise DeploymentCheckpointLedgerError("checkpoint root ancestry mismatch")
            published = _parse_utc(row.published_at)
            if previous_time is not None and published < previous_time:
                raise DeploymentCheckpointLedgerError("checkpoint publication time regressed")
            if row.checkpoint_root_sha256 in roots:
                raise DeploymentCheckpointLedgerError("checkpoint publication root replay/rollback detected")
            if previous is not None:
                _validate_evolution(previous.checkpoint, row.checkpoint)
            roots.add(row.checkpoint_root_sha256)
            previous_time = published
            rows.append(row)
        return tuple(rows)

    def publish(self, checkpoint: DeploymentEvidenceCheckpoint, *,
                published_at: str | None = None) -> DeploymentCheckpointPublication:
        if not verify_deployment_evidence_checkpoint(checkpoint):
            raise ValueError("deployment checkpoint failed verification")
        if published_at is None:
            stamp = datetime.now(UTC).isoformat()
        else:
            _parse_utc(published_at)
            stamp = published_at
        with self._lease.acquire():
            rows = list(self._load_verified())
            if rows and hmac.compare_digest(rows[-1].checkpoint_root_sha256, checkpoint.root_sha256):
                return rows[-1]
            if any(hmac.compare_digest(row.checkpoint_root_sha256, checkpoint.root_sha256) for row in rows):
                raise DeploymentCheckpointLedgerError("checkpoint rollback/republication detected")
            previous = rows[-1] if rows else None
            if previous is not None:
                _validate_evolution(previous.checkpoint, checkpoint)
                if _parse_utc(stamp) < _parse_utc(previous.published_at):
                    raise DeploymentCheckpointLedgerError("checkpoint publication time regressed")
            draft = DeploymentCheckpointPublication(
                version=DEPLOYMENT_CHECKPOINT_LEDGER_VERSION,
                sequence=len(rows) + 1,
                checkpoint=checkpoint,
                checkpoint_root_sha256=checkpoint.root_sha256,
                checkpoint_attestation_sha256=checkpoint.attestation_sha256,
                published_at=stamp,
                previous_checkpoint_root_sha256=previous.checkpoint_root_sha256 if previous else "",
                previous_sha256=previous.sha256 if previous else "",
                sha256="",
            )
            digest = canonical_json_sha256(_publication_payload(draft))
            publication = DeploymentCheckpointPublication(
                draft.version,
                draft.sequence,
                draft.checkpoint,
                draft.checkpoint_root_sha256,
                draft.checkpoint_attestation_sha256,
                draft.published_at,
                draft.previous_checkpoint_root_sha256,
                draft.previous_sha256,
                digest,
            )
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(canonical_json_text(asdict(publication)) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return publication

    def history(self) -> tuple[DeploymentCheckpointPublication, ...]:
        with self._lease.acquire():
            return self._load_verified()

    def latest(self) -> DeploymentCheckpointPublication | None:
        rows = self.history()
        return rows[-1] if rows else None

    def status(self) -> dict[str, Any]:
        rows = self.history()
        latest = rows[-1] if rows else None
        return {
            "version": DEPLOYMENT_CHECKPOINT_LEDGER_VERSION,
            "publications": len(rows),
            "head_sha256": latest.sha256 if latest else "",
            "checkpoint_root_sha256": latest.checkpoint_root_sha256 if latest else "",
            "checkpoint_attestation_sha256": latest.checkpoint_attestation_sha256 if latest else "",
            "latest_published_at": latest.published_at if latest else "",
            "verified": True,
            "cross_process_locking": True,
            "lock_backend": self._lease.backend,
        }
