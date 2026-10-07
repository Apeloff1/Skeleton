"""Durable immutable session-journal manifests for finalized AI executions.

The authoritative decision journal is global and append-only.  Recovery should
not rescan that entire history just to rediscover which global event sequences
belonged to one finalized session.  This module persists the already-verified
session projection next to its historical journal root and finalization
identity.

The manifest does not replace the authoritative journal.  Readers must still
verify every projected event against the journal at the bound historical root.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.session_journal import SessionJournalEvidence
from skeleton.shells.ai.store_protocol import VersionedStateBackend


def _digest(name: str, value: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be 64-character digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be SHA-256 hex") from exc
    return value.lower()


def _identity(
    name: str,
    value: str,
    *,
    maximum: int,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
    ):
        raise ValueError(f"invalid {name}")
    return value


@dataclass(frozen=True)
class DurableSessionJournalManifest:
    schema_version: int
    finalization_id: str
    session_id: str
    journal_root: str
    journal_evidence: SessionJournalEvidence
    stored_at: float

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported durable session-journal manifest schema"
            )
        object.__setattr__(
            self,
            "finalization_id",
            _identity(
                "finalization_id",
                self.finalization_id,
                maximum=256,
            ),
        )
        object.__setattr__(
            self,
            "session_id",
            _identity(
                "session_id",
                self.session_id,
                maximum=160,
            ),
        )
        object.__setattr__(
            self,
            "journal_root",
            _digest(
                "journal_root",
                self.journal_root,
            ),
        )
        if not isinstance(
            self.journal_evidence,
            SessionJournalEvidence,
        ):
            raise TypeError(
                "journal_evidence must be SessionJournalEvidence"
            )
        if (
            self.journal_evidence.session_id
            != self.session_id
        ):
            raise ValueError(
                "session-journal manifest session binding mismatch"
            )
        if (
            isinstance(self.stored_at, bool)
            or not isinstance(
                self.stored_at,
                (int, float),
            )
            or not math.isfinite(
                float(self.stored_at)
            )
            or float(self.stored_at) < 0.0
        ):
            raise ValueError(
                "stored_at must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "stored_at",
            float(self.stored_at),
        )

    @property
    def journal_digest(self) -> str:
        return self.journal_evidence.digest

    @property
    def first_sequence(self) -> int | None:
        if not self.journal_evidence.events:
            return None
        return self.journal_evidence.events[0].global_sequence

    @property
    def last_sequence(self) -> int | None:
        if not self.journal_evidence.events:
            return None
        return self.journal_evidence.events[-1].global_sequence

    @property
    def event_count(self) -> int:
        return len(self.journal_evidence.events)

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(
                include_digest=False
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "schema_version": self.schema_version,
            "finalization_id": self.finalization_id,
            "session_id": self.session_id,
            "journal_root": self.journal_root,
            "journal_evidence": (
                self.journal_evidence.to_dict()
            ),
            "journal_digest": self.journal_digest,
            "first_sequence": self.first_sequence,
            "last_sequence": self.last_sequence,
            "event_count": self.event_count,
            "stored_at": self.stored_at,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableSessionJournalHead:
    session_id: str
    finalization_id: str
    journal_root: str
    journal_digest: str
    event_count: int
    last_sequence: int | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "session_id",
            _identity(
                "session_id",
                self.session_id,
                maximum=160,
            ),
        )
        object.__setattr__(
            self,
            "finalization_id",
            _identity(
                "finalization_id",
                self.finalization_id,
                maximum=256,
            ),
        )
        for name in (
            "journal_root",
            "journal_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )
        if (
            isinstance(self.event_count, bool)
            or not isinstance(
                self.event_count,
                int,
            )
            or self.event_count < 0
        ):
            raise ValueError(
                "event_count must be non-negative integer"
            )
        if self.last_sequence is not None and (
            isinstance(
                self.last_sequence,
                bool,
            )
            or not isinstance(
                self.last_sequence,
                int,
            )
            or self.last_sequence <= 0
        ):
            raise ValueError(
                "last_sequence must be positive when present"
            )
        if bool(self.event_count) != (
            self.last_sequence is not None
        ):
            raise ValueError(
                "event_count and last_sequence presence mismatch"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "finalization_id": self.finalization_id,
            "journal_root": self.journal_root,
            "journal_digest": self.journal_digest,
            "event_count": self.event_count,
            "last_sequence": self.last_sequence,
        }


@dataclass(frozen=True)
class StoredDurableSessionJournal:
    revision: int
    manifest: DurableSessionJournalManifest

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError(
                "session-journal revision must be positive"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "manifest": self.manifest.to_dict(),
        }


@dataclass(frozen=True)
class DurableSessionJournalCommit:
    stored: StoredDurableSessionJournal
    head_revision: int
    head: DurableSessionJournalHead
    head_advanced: bool

    def __post_init__(self) -> None:
        if (
            isinstance(self.head_revision, bool)
            or not isinstance(
                self.head_revision,
                int,
            )
            or self.head_revision <= 0
        ):
            raise ValueError(
                "session-journal head revision must be positive"
            )
        if not isinstance(
            self.head_advanced,
            bool,
        ):
            raise ValueError(
                "head_advanced must be bool"
            )
        if (
            self.stored.manifest.session_id
            != self.head.session_id
        ):
            raise ValueError(
                "session-journal commit session mismatch"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "stored": self.stored.to_dict(),
            "head_revision": self.head_revision,
            "head": self.head.to_dict(),
            "head_advanced": self.head_advanced,
        }


class DurableSessionJournalConflict(RuntimeError):
    pass


class DurableSessionJournalCorruption(RuntimeError):
    pass


class DurableSessionJournalStore:
    """CAS-backed immutable session-journal manifests."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = "shell-ai-durable-session-journal",
        max_events_per_manifest: int = 16_384,
        max_retries: int = 16,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid durable session-journal namespace"
            )
        if (
            isinstance(
                max_events_per_manifest,
                bool,
            )
            or not isinstance(
                max_events_per_manifest,
                int,
            )
            or max_events_per_manifest <= 0
        ):
            raise ValueError(
                "max_events_per_manifest must be positive integer"
            )
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or not 1 <= max_retries <= 64
        ):
            raise ValueError(
                "max_retries outside supported range"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.backend = backend
        self.namespace = namespace
        self.max_events_per_manifest = (
            max_events_per_manifest
        )
        self.max_retries = max_retries
        self._clock = clock

    @staticmethod
    def _manifest_key(
        finalization_id: str,
    ) -> str:
        finalization_id = _identity(
            "finalization_id",
            finalization_id,
            maximum=256,
        )
        return "manifest:" + hashlib.sha256(
            finalization_id.encode()
        ).hexdigest()

    @staticmethod
    def _head_key(
        session_id: str,
    ) -> str:
        session_id = _identity(
            "session_id",
            session_id,
            maximum=160,
        )
        return "head:" + hashlib.sha256(
            session_id.encode()
        ).hexdigest()

    def get(
        self,
        finalization_id: str,
    ) -> StoredDurableSessionJournal | None:
        record = self.backend.get(
            self.namespace,
            self._manifest_key(
                finalization_id
            ),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableSessionJournalManifest,
        ):
            raise DurableSessionJournalCorruption(
                "session-journal manifest has invalid backend type"
            )
        return StoredDurableSessionJournal(
            record.revision,
            record.value,
        )

    def head(
        self,
        session_id: str,
    ) -> tuple[
        int,
        DurableSessionJournalHead,
    ] | None:
        record = self.backend.get(
            self.namespace,
            self._head_key(
                session_id
            ),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableSessionJournalHead,
        ):
            raise DurableSessionJournalCorruption(
                "session-journal head has invalid backend type"
            )
        return record.revision, record.value

    @staticmethod
    def _head_for(
        manifest: DurableSessionJournalManifest,
    ) -> DurableSessionJournalHead:
        return DurableSessionJournalHead(
            manifest.session_id,
            manifest.finalization_id,
            manifest.journal_root,
            manifest.journal_digest,
            manifest.event_count,
            manifest.last_sequence,
        )

    def _store_manifest(
        self,
        manifest: DurableSessionJournalManifest,
    ) -> StoredDurableSessionJournal:
        key = self._manifest_key(
            manifest.finalization_id
        )
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is not None:
            if not isinstance(
                existing.value,
                DurableSessionJournalManifest,
            ):
                raise DurableSessionJournalCorruption(
                    "session-journal manifest has invalid backend type"
                )
            if existing.value.digest != manifest.digest:
                raise DurableSessionJournalConflict(
                    "finalization_id already binds different session journal"
                )
            return StoredDurableSessionJournal(
                existing.revision,
                existing.value,
            )
        try:
            record = self.backend.put_if_absent(
                self.namespace,
                key,
                manifest,
            )
            return StoredDurableSessionJournal(
                record.revision,
                manifest,
            )
        except DistributedStateConflict:
            winner = self.backend.get(
                self.namespace,
                key,
            )
            if (
                winner is None
                or not isinstance(
                    winner.value,
                    DurableSessionJournalManifest,
                )
            ):
                raise
            if winner.value.digest != manifest.digest:
                raise DurableSessionJournalConflict(
                    "concurrent session-journal manifest differs"
                )
            return StoredDurableSessionJournal(
                winner.revision,
                winner.value,
            )

    def put(
        self,
        *,
        finalization_id: str,
        journal_root: str,
        journal_evidence: SessionJournalEvidence,
    ) -> DurableSessionJournalCommit:
        if not isinstance(
            journal_evidence,
            SessionJournalEvidence,
        ):
            raise TypeError(
                "journal_evidence must be SessionJournalEvidence"
            )
        if (
            len(journal_evidence.events)
            > self.max_events_per_manifest
        ):
            raise DurableSessionJournalConflict(
                "session journal exceeds manifest event bound"
            )
        manifest = DurableSessionJournalManifest(
            1,
            finalization_id,
            journal_evidence.session_id,
            journal_root,
            journal_evidence,
            self._clock(),
        )
        stored = self._store_manifest(
            manifest
        )
        candidate = self._head_for(
            stored.manifest
        )
        key = self._head_key(
            candidate.session_id
        )

        for _ in range(self.max_retries):
            current = self.backend.get(
                self.namespace,
                key,
            )
            if current is None:
                try:
                    created = (
                        self.backend.put_if_absent(
                            self.namespace,
                            key,
                            candidate,
                        )
                    )
                    return (
                        DurableSessionJournalCommit(
                            stored,
                            created.revision,
                            candidate,
                            True,
                        )
                    )
                except DistributedStateConflict:
                    continue
            if not isinstance(
                current.value,
                DurableSessionJournalHead,
            ):
                raise DurableSessionJournalCorruption(
                    "session-journal head has invalid backend type"
                )
            existing = current.value
            existing_sequence = (
                existing.last_sequence or 0
            )
            candidate_sequence = (
                candidate.last_sequence or 0
            )
            if existing_sequence > candidate_sequence:
                return DurableSessionJournalCommit(
                    stored,
                    current.revision,
                    existing,
                    False,
                )
            if existing_sequence == candidate_sequence:
                if (
                    existing.journal_digest
                    != candidate.journal_digest
                    or existing.journal_root
                    != candidate.journal_root
                ):
                    raise DurableSessionJournalConflict(
                        "same session journal position has conflicting manifest"
                    )
                return DurableSessionJournalCommit(
                    stored,
                    current.revision,
                    existing,
                    False,
                )
            try:
                updated = (
                    self.backend.compare_and_swap(
                        self.namespace,
                        key,
                        expected_revision=(
                            current.revision
                        ),
                        value=candidate,
                    )
                )
                return DurableSessionJournalCommit(
                    stored,
                    updated.revision,
                    candidate,
                    True,
                )
            except DistributedStateConflict:
                continue

        raise DurableSessionJournalConflict(
            "session-journal head CAS retry bound exceeded"
        )

    def require(
        self,
        finalization_id: str,
        *,
        journal_digest: str = "",
        journal_root: str = "",
    ) -> StoredDurableSessionJournal:
        stored = self.get(
            finalization_id
        )
        if stored is None:
            raise DurableSessionJournalConflict(
                "durable session-journal manifest is missing"
            )
        if journal_digest:
            journal_digest = _digest(
                "journal_digest",
                journal_digest,
            )
            if (
                stored.manifest.journal_digest
                != journal_digest
            ):
                raise DurableSessionJournalConflict(
                    "durable session-journal digest mismatch"
                )
        if journal_root:
            journal_root = _digest(
                "journal_root",
                journal_root,
            )
            if (
                stored.manifest.journal_root
                != journal_root
            ):
                raise DurableSessionJournalConflict(
                    "durable session-journal root mismatch"
                )
        return stored

    def current_session(
        self,
        session_id: str,
    ) -> StoredDurableSessionJournal | None:
        head = self.head(
            session_id
        )
        if head is None:
            return None
        _, pointer = head
        stored = self.get(
            pointer.finalization_id
        )
        if stored is None:
            raise DurableSessionJournalCorruption(
                "session-journal head references missing manifest"
            )
        manifest = stored.manifest
        if (
            manifest.session_id != session_id
            or manifest.journal_root
            != pointer.journal_root
            or manifest.journal_digest
            != pointer.journal_digest
            or manifest.event_count
            != pointer.event_count
            or manifest.last_sequence
            != pointer.last_sequence
        ):
            raise DurableSessionJournalCorruption(
                "session-journal head/manifest mismatch"
            )
        return stored

    def verify_manifest(
        self,
        finalization_id: str,
        *,
        journal,
    ) -> bool:
        stored = self.get(
            finalization_id
        )
        if stored is None:
            return False
        manifest = stored.manifest
        snapshot_at = getattr(
            journal,
            "snapshot_at",
            None,
        )
        root_is_ancestor = getattr(
            journal,
            "root_is_ancestor",
            None,
        )
        get_by_sequence = getattr(
            journal,
            "get_by_sequence",
            None,
        )
        if not (
            callable(snapshot_at)
            and callable(root_is_ancestor)
            and callable(get_by_sequence)
        ):
            return False
        try:
            if not root_is_ancestor(
                manifest.journal_root
            ):
                return False
            for projected in (
                manifest.journal_evidence.events
            ):
                event = get_by_sequence(
                    projected.global_sequence,
                    repair_missing=False,
                )
                if (
                    event.event_hash
                    != projected.event_hash
                    or event.kind
                    != projected.kind
                    or event.proposal_id
                    != projected.proposal_id
                    or event.session_id
                    != manifest.session_id
                ):
                    return False
        except Exception:
            return False
        return True
