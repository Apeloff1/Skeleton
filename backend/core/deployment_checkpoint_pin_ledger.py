"""Durable runtime ingestion for externally signed deployment-checkpoint pins.

The server never owns witness private keys. External witnesses sign checkpoint
publication heads and submit receipts. This ledger validates each receipt against an
out-of-band trusted-key registry and the local append-only checkpoint publication
history, then persists only verified evidence in a hash-chained JSONL journal.

Quorum is freshness-bounded and independence-group based. Replaying the same receipt
is idempotent; a different receipt from the same witness for the same publication is
rejected rather than averaged away.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime, timedelta
import hmac
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from core.canonical_json import CanonicalJSONError, canonical_json_clone, canonical_json_sha256, canonical_json_text
from core.deployment_checkpoint_ledger import DeploymentCheckpointLedger, DeploymentCheckpointPublication, _restore_publication
from core.deployment_checkpoint_witness import (
    DEPLOYMENT_CHECKPOINT_PIN_VERSION,
    DeploymentCheckpointPinBundle,
    DeploymentCheckpointPinReceipt,
    build_deployment_checkpoint_pin_bundle,
    verify_deployment_checkpoint_pin,
)
from core.file_lease import FileLease
from core.signed_transparency_witness import SignedWitnessStatement, public_key_fingerprint
from core.transparency_witness import TrustedWitness

DEPLOYMENT_CHECKPOINT_PIN_LEDGER_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EVENT_KEYS = {"version", "sequence", "receipt", "previous_sha256", "sha256"}
_RECEIPT_KEYS = {"version", "publication", "witness", "receipt_sha256"}
_WITNESS_KEYS = {field.name for field in fields(SignedWitnessStatement)}


class DeploymentCheckpointPinLedgerError(RuntimeError):
    pass


class DeploymentCheckpointPinRejected(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DeploymentCheckpointPinEvent:
    version: int
    sequence: int
    receipt: DeploymentCheckpointPinReceipt
    previous_sha256: str
    sha256: str


@dataclass(frozen=True, slots=True)
class DeploymentCheckpointPinQuorum:
    publication_sequence: int
    publication_sha256: str
    trusted_receipts: int
    fresh_receipts: int
    stale_receipts: int
    independent_groups: int
    required_groups: int
    max_age_seconds: int
    reached: bool
    witness_ids: tuple[str, ...]
    groups: tuple[str, ...]
    attestation_sha256: str


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _canonical_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be canonical non-empty text")
    return value


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("checkpoint pin timestamp must be canonical text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("checkpoint pin timestamp is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("checkpoint pin timestamp must be timezone-aware")
    normalized = parsed.astimezone(UTC).isoformat()
    if value.replace("Z", "+00:00") != normalized:
        raise ValueError("checkpoint pin timestamp must be normalized to UTC")
    return parsed.astimezone(UTC)


def _normalize_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if not isinstance(value, datetime):
        raise ValueError("checkpoint pin quorum time must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("checkpoint pin quorum time must be timezone-aware")
    return value.astimezone(UTC)


def _strict_json_loads(text: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=reject_duplicates)


def _event_payload(event: DeploymentCheckpointPinEvent) -> dict[str, Any]:
    return {
        "version": event.version,
        "sequence": event.sequence,
        "receipt": asdict(event.receipt),
        "previous_sha256": event.previous_sha256,
    }


def _restore_receipt(raw: Any) -> DeploymentCheckpointPinReceipt:
    if not isinstance(raw, Mapping) or set(raw) != _RECEIPT_KEYS:
        raise DeploymentCheckpointPinLedgerError("checkpoint pin receipt schema mismatch")
    if type(raw.get("version")) is not int or raw["version"] != DEPLOYMENT_CHECKPOINT_PIN_VERSION:
        raise DeploymentCheckpointPinLedgerError("checkpoint pin receipt version malformed")
    witness_raw = raw.get("witness")
    if not isinstance(witness_raw, Mapping) or set(witness_raw) != _WITNESS_KEYS:
        raise DeploymentCheckpointPinLedgerError("checkpoint pin witness schema mismatch")
    try:
        publication = _restore_publication(canonical_json_clone(raw.get("publication")))
        witness = SignedWitnessStatement(**canonical_json_clone(dict(witness_raw)))
    except (CanonicalJSONError, TypeError, ValueError) as exc:
        raise DeploymentCheckpointPinLedgerError("checkpoint pin receipt is not portable canonical JSON") from exc
    receipt_sha = raw.get("receipt_sha256")
    if not _is_sha(receipt_sha):
        raise DeploymentCheckpointPinLedgerError("checkpoint pin receipt digest malformed")
    return DeploymentCheckpointPinReceipt(raw["version"], publication, witness, receipt_sha)


def _restore_event(raw: Any) -> DeploymentCheckpointPinEvent:
    if not isinstance(raw, Mapping) or set(raw) != _EVENT_KEYS:
        raise DeploymentCheckpointPinLedgerError("checkpoint pin event schema mismatch")
    if type(raw.get("version")) is not int or raw["version"] != DEPLOYMENT_CHECKPOINT_PIN_LEDGER_VERSION:
        raise DeploymentCheckpointPinLedgerError("checkpoint pin event version malformed")
    if type(raw.get("sequence")) is not int or raw["sequence"] < 1:
        raise DeploymentCheckpointPinLedgerError("checkpoint pin event sequence malformed")
    previous = raw.get("previous_sha256")
    digest = raw.get("sha256")
    if not isinstance(previous, str) or (previous and not _is_sha(previous)):
        raise DeploymentCheckpointPinLedgerError("checkpoint pin event ancestry malformed")
    if not _is_sha(digest):
        raise DeploymentCheckpointPinLedgerError("checkpoint pin event digest malformed")
    receipt = _restore_receipt(raw.get("receipt"))
    event = DeploymentCheckpointPinEvent(raw["version"], raw["sequence"], receipt, previous, digest)
    try:
        expected = canonical_json_sha256(_event_payload(event))
    except CanonicalJSONError as exc:
        raise DeploymentCheckpointPinLedgerError("checkpoint pin event is not canonical JSON") from exc
    if not hmac.compare_digest(expected, event.sha256):
        raise DeploymentCheckpointPinLedgerError("checkpoint pin event hash mismatch")
    return event


class DeploymentCheckpointPinLedger:
    def __init__(
        self,
        root: str | Path,
        *,
        checkpoint_ledger: DeploymentCheckpointLedger,
        trusted_witnesses: Iterable[TrustedWitness] = (),
        required_groups: int = 3,
        max_age_seconds: int = 3600,
    ) -> None:
        if not isinstance(checkpoint_ledger, DeploymentCheckpointLedger):
            raise ValueError("checkpoint_ledger must be a DeploymentCheckpointLedger")
        if type(required_groups) is not int or not 1 <= required_groups <= 64:
            raise ValueError("checkpoint pin quorum must be an integer between 1 and 64")
        if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 604800:
            raise ValueError("checkpoint pin max age must be an integer between 1 and 604800")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "deployment-checkpoint-pins.jsonl"
        self._lease = FileLease(self.root / ".deployment-checkpoint-pins.lock")
        self.checkpoint_ledger = checkpoint_ledger
        self.required_groups = required_groups
        self.max_age_seconds = max_age_seconds
        self._trusted = self._normalize_registry(trusted_witnesses)
        local = self._publication_index()
        with self._lease.acquire():
            if not self.path.exists():
                self.path.touch()
            self._load_verified(local)

    @staticmethod
    def _normalize_registry(rows: Iterable[TrustedWitness]) -> dict[str, TrustedWitness]:
        registry: dict[str, TrustedWitness] = {}
        for row in rows:
            if not isinstance(row, TrustedWitness):
                raise ValueError("checkpoint pin trust registry contains unsupported entry")
            witness_id = _canonical_text(row.id, "trusted witness id")
            group = _canonical_text(row.independence_group, "trusted witness independence_group")
            if type(row.enabled) is not bool:
                raise ValueError("trusted witness enabled must be boolean")
            if witness_id in registry:
                raise ValueError(f"duplicate trusted checkpoint witness: {witness_id}")
            if row.enabled:
                if not isinstance(row.public_key_b64, str) or not row.public_key_b64:
                    raise ValueError("enabled checkpoint witness requires pinned Ed25519 public key")
                try:
                    public_key_fingerprint(row.public_key_b64)
                except ValueError as exc:
                    raise ValueError("enabled checkpoint witness has malformed Ed25519 public key") from exc
                registry[witness_id] = TrustedWitness(witness_id, group, True, row.public_key_b64)
        return registry

    def _publication_index(self) -> dict[tuple[int, str], DeploymentCheckpointPublication]:
        rows = self.checkpoint_ledger.history()
        return {(row.sequence, row.sha256): row for row in rows}

    def _verify_receipt(
        self,
        receipt: DeploymentCheckpointPinReceipt,
        local: Mapping[tuple[int, str], DeploymentCheckpointPublication],
    ) -> TrustedWitness:
        if not isinstance(receipt, DeploymentCheckpointPinReceipt):
            raise DeploymentCheckpointPinRejected("checkpoint pin receipt type mismatch")
        publication = local.get((receipt.publication.sequence, receipt.publication.sha256))
        if publication is None or publication != receipt.publication:
            raise DeploymentCheckpointPinRejected("checkpoint pin does not target the local verified publication history")
        witness = self._trusted.get(receipt.witness.witness_id)
        if witness is None:
            raise DeploymentCheckpointPinRejected("checkpoint pin witness is not trusted")
        if not verify_deployment_checkpoint_pin(
            receipt,
            public_key_b64=witness.public_key_b64,
            expected_group=witness.independence_group,
            expected_publication_head_sha256=publication.sha256,
        ):
            raise DeploymentCheckpointPinRejected("checkpoint pin signature or binding failed verification")
        return witness

    def _load_verified(
        self,
        local: Mapping[tuple[int, str], DeploymentCheckpointPublication],
    ) -> tuple[DeploymentCheckpointPinEvent, ...]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise DeploymentCheckpointPinLedgerError("checkpoint pin ledger unreadable") from exc
        rows: list[DeploymentCheckpointPinEvent] = []
        seen: dict[tuple[str, str], str] = {}
        for line in lines:
            if not line.strip():
                raise DeploymentCheckpointPinLedgerError("checkpoint pin ledger contains blank record")
            try:
                raw = _strict_json_loads(line)
            except (json.JSONDecodeError, ValueError) as exc:
                raise DeploymentCheckpointPinLedgerError("checkpoint pin ledger malformed") from exc
            event = _restore_event(raw)
            if event.sequence != len(rows) + 1:
                raise DeploymentCheckpointPinLedgerError("checkpoint pin event sequence mismatch")
            expected_previous = rows[-1].sha256 if rows else ""
            if event.previous_sha256 != expected_previous:
                raise DeploymentCheckpointPinLedgerError("checkpoint pin event ancestry mismatch")
            try:
                self._verify_receipt(event.receipt, local)
            except DeploymentCheckpointPinRejected as exc:
                raise DeploymentCheckpointPinLedgerError(str(exc)) from exc
            identity = (event.receipt.publication.sha256, event.receipt.witness.witness_id)
            existing = seen.get(identity)
            if existing is not None and not hmac.compare_digest(existing, event.receipt.receipt_sha256):
                raise DeploymentCheckpointPinLedgerError("checkpoint witness equivocation detected for one publication")
            if existing is not None:
                raise DeploymentCheckpointPinLedgerError("checkpoint pin ledger contains duplicate witness receipt")
            seen[identity] = event.receipt.receipt_sha256
            rows.append(event)
        return tuple(rows)

    def observe(self, receipt: DeploymentCheckpointPinReceipt) -> DeploymentCheckpointPinEvent:
        local = self._publication_index()
        self._verify_receipt(receipt, local)
        with self._lease.acquire():
            rows = list(self._load_verified(local))
            identity = (receipt.publication.sha256, receipt.witness.witness_id)
            for event in rows:
                current = (event.receipt.publication.sha256, event.receipt.witness.witness_id)
                if current != identity:
                    continue
                if hmac.compare_digest(event.receipt.receipt_sha256, receipt.receipt_sha256):
                    return event
                raise DeploymentCheckpointPinRejected("trusted witness submitted conflicting pin for publication")
            draft = DeploymentCheckpointPinEvent(
                DEPLOYMENT_CHECKPOINT_PIN_LEDGER_VERSION,
                len(rows) + 1,
                receipt,
                rows[-1].sha256 if rows else "",
                "",
            )
            digest = canonical_json_sha256(_event_payload(draft))
            event = DeploymentCheckpointPinEvent(
                draft.version, draft.sequence, draft.receipt, draft.previous_sha256, digest,
            )
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(canonical_json_text(asdict(event)) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return event

    def snapshot(self) -> tuple[DeploymentCheckpointPinEvent, ...]:
        local = self._publication_index()
        with self._lease.acquire():
            return self._load_verified(local)

    def quorum(
        self,
        *,
        publication_sequence: int | None = None,
        now: datetime | None = None,
    ) -> DeploymentCheckpointPinQuorum | None:
        publications = self.checkpoint_ledger.history()
        if not publications:
            return None
        if publication_sequence is None:
            publication = publications[-1]
        else:
            if type(publication_sequence) is not int or publication_sequence < 1:
                raise ValueError("publication_sequence must be a positive integer")
            publication = next((row for row in publications if row.sequence == publication_sequence), None)
            if publication is None:
                raise KeyError(publication_sequence)
        when = _normalize_now(now)
        earliest = when - timedelta(seconds=self.max_age_seconds)
        events = [row for row in self.snapshot() if hmac.compare_digest(row.receipt.publication.sha256, publication.sha256)]
        trusted = len(events)
        fresh: list[DeploymentCheckpointPinEvent] = []
        stale = 0
        groups: set[str] = set()
        witness_ids: set[str] = set()
        for event in events:
            observed = _parse_utc(event.receipt.witness.observed_at)
            if observed > when or observed < earliest:
                stale += 1
                continue
            fresh.append(event)
            witness = self._trusted[event.receipt.witness.witness_id]
            groups.add(witness.independence_group)
            witness_ids.add(witness.id)
        payload = {
            "publication_sequence": publication.sequence,
            "publication_sha256": publication.sha256,
            "trusted_receipts": trusted,
            "fresh_receipts": len(fresh),
            "stale_receipts": stale,
            "independent_groups": len(groups),
            "required_groups": self.required_groups,
            "max_age_seconds": self.max_age_seconds,
            "reached": len(groups) >= self.required_groups,
            "witness_ids": sorted(witness_ids),
            "groups": sorted(groups),
        }
        attestation = canonical_json_sha256(payload)
        return DeploymentCheckpointPinQuorum(
            publication.sequence,
            publication.sha256,
            trusted,
            len(fresh),
            stale,
            len(groups),
            self.required_groups,
            self.max_age_seconds,
            len(groups) >= self.required_groups,
            tuple(sorted(witness_ids)),
            tuple(sorted(groups)),
            attestation,
        )

    def portable_bundle(
        self,
        *,
        publication_sequence: int | None = None,
        now: datetime | None = None,
    ) -> DeploymentCheckpointPinBundle:
        when = _normalize_now(now)
        quorum = self.quorum(publication_sequence=publication_sequence, now=when)
        if quorum is None or not quorum.reached:
            raise DeploymentCheckpointPinRejected("checkpoint pin quorum has not been reached")
        publication = next(
            row for row in self.checkpoint_ledger.history()
            if row.sequence == quorum.publication_sequence
        )
        earliest = when - timedelta(seconds=self.max_age_seconds)
        receipts = []
        for event in self.snapshot():
            if not hmac.compare_digest(event.receipt.publication.sha256, publication.sha256):
                continue
            observed = _parse_utc(event.receipt.witness.observed_at)
            if earliest <= observed <= when:
                receipts.append(event.receipt)
        return build_deployment_checkpoint_pin_bundle(
            publication,
            receipts,
            required_groups=self.required_groups,
        )

    def status(self, *, now: datetime | None = None) -> dict[str, Any]:
        rows = self.snapshot()
        quorum = self.quorum(now=now)
        configured_groups = len({row.independence_group for row in self._trusted.values()})
        return {
            "version": DEPLOYMENT_CHECKPOINT_PIN_LEDGER_VERSION,
            "events": len(rows),
            "head_sha256": rows[-1].sha256 if rows else "",
            "trusted_witnesses": len(self._trusted),
            "configured_independence_groups": configured_groups,
            "required_groups": self.required_groups,
            "max_age_seconds": self.max_age_seconds,
            "current_quorum": None if quorum is None else asdict(quorum),
            "verified": True,
            "cross_process_locking": True,
            "lock_backend": self._lease.backend,
        }
