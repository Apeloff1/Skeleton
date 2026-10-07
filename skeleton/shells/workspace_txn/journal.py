"""Tamper-evident transaction journal with optional durable persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import threading
from types import MappingProxyType
from typing import Any, Mapping

from skeleton.shells.provenance import canonical_json

GENESIS = "0" * 64


class JournalPersistenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class JournalEvent:
    sequence: int
    previous_hash: str
    event_hash: str
    transaction_id: str
    kind: str
    created_at: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError("journal sequence must be positive")
        if len(self.previous_hash) != 64 or len(self.event_hash) != 64:
            raise ValueError("journal hashes must be SHA-256 hex")
        if any(
            ch not in "0123456789abcdef"
            for ch in self.previous_hash + self.event_hash
        ):
            raise ValueError("journal hashes must be lowercase SHA-256 hex")
        if not self.transaction_id or not self.kind or not self.created_at:
            raise ValueError("journal event identity fields are required")
        object.__setattr__(
            self,
            "payload",
            MappingProxyType(dict(self.payload)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
            "transaction_id": self.transaction_id,
            "kind": self.kind,
            "created_at": self.created_at,
            "payload": dict(self.payload),
        }


class TransactionJournal:
    """Append-only hash chain with optional fsync-backed JSONL storage.

    With a storage path, each event is persisted before it becomes visible in
    memory. A crash may leave only the final append truncated; restart loading
    safely discards and truncates that incomplete tail after verifying every
    complete prior event.
    """

    def __init__(
        self,
        *,
        max_events: int = 1_000_000,
        storage_path: Path | str | None = None,
        max_record_bytes: int = 64 * 1024,
        fsync: bool = True,
    ) -> None:
        if (
            isinstance(max_events, bool)
            or not isinstance(max_events, int)
            or max_events <= 0
        ):
            raise ValueError("max_events must be positive")
        if (
            isinstance(max_record_bytes, bool)
            or not isinstance(max_record_bytes, int)
            or max_record_bytes <= 0
        ):
            raise ValueError("max_record_bytes must be positive")
        if not isinstance(fsync, bool):
            raise ValueError("fsync must be boolean")
        self.max_events = max_events
        self.max_record_bytes = max_record_bytes
        self.storage_path = (
            None if storage_path is None else Path(storage_path).expanduser()
        )
        self.fsync = fsync
        self._events: list[JournalEvent] = []
        self._lock = threading.RLock()
        self._recovered_truncated_tail = False
        if self.storage_path is not None and self.storage_path.exists():
            self._load()

    @property
    def durable(self) -> bool:
        return self.storage_path is not None

    @property
    def recovered_truncated_tail(self) -> bool:
        return self._recovered_truncated_tail

    def _require_parent_directory(self) -> Path:
        assert self.storage_path is not None
        parent = self.storage_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        try:
            metadata = parent.lstat()
        except OSError as exc:
            raise JournalPersistenceError(
                "transaction journal parent is unavailable"
            ) from exc
        if not stat.S_ISDIR(metadata.st_mode):
            raise JournalPersistenceError(
                "transaction journal parent must be a real directory"
            )
        return parent

    def require_external_to_workspace(self, workspace_root: Path | str) -> None:
        if self.storage_path is None:
            return
        root = Path(workspace_root).expanduser().resolve(strict=True)
        journal = self.storage_path.resolve(strict=False)
        if journal == root or root in journal.parents:
            raise JournalPersistenceError(
                "transaction journal must be outside the protected workspace"
            )

    @staticmethod
    def _hash(
        sequence: int,
        previous: str,
        transaction_id: str,
        kind: str,
        created_at: str,
        payload: Mapping[str, Any],
    ) -> str:
        return hashlib.sha256(
            canonical_json(
                {
                    "sequence": sequence,
                    "previous_hash": previous,
                    "transaction_id": transaction_id,
                    "kind": kind,
                    "created_at": created_at,
                    "payload": dict(payload),
                }
            )
        ).hexdigest()

    @classmethod
    def _event_from_mapping(cls, value: object) -> JournalEvent:
        if not isinstance(value, dict):
            raise JournalPersistenceError(
                "journal record must be a JSON object"
            )
        sequence = value.get("sequence")
        previous_hash = value.get("previous_hash")
        event_hash = value.get("event_hash")
        transaction_id = value.get("transaction_id")
        kind = value.get("kind")
        created_at = value.get("created_at")
        payload = value.get("payload")
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise JournalPersistenceError(
                "journal record sequence is invalid"
            )
        if not all(
            isinstance(item, str)
            for item in (
                previous_hash,
                event_hash,
                transaction_id,
                kind,
                created_at,
            )
        ):
            raise JournalPersistenceError(
                "journal record text field is invalid"
            )
        if not isinstance(payload, dict):
            raise JournalPersistenceError(
                "journal record payload is invalid"
            )
        try:
            return JournalEvent(
                sequence=sequence,
                previous_hash=previous_hash,
                event_hash=event_hash,
                transaction_id=transaction_id,
                kind=kind,
                created_at=created_at,
                payload=payload,
            )
        except ValueError as exc:
            raise JournalPersistenceError(
                "journal record failed validation"
            ) from exc

    def _load(self) -> None:
        assert self.storage_path is not None
        try:
            metadata = self.storage_path.lstat()
        except OSError as exc:
            raise JournalPersistenceError(
                "transaction journal is unavailable"
            ) from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise JournalPersistenceError(
                "transaction journal must be a regular file"
            )

        loaded: list[JournalEvent] = []
        good_end = 0
        truncated_tail = False
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(self.storage_path, flags)
            with os.fdopen(fd, "rb") as handle:
                metadata = os.fstat(handle.fileno())
                if not stat.S_ISREG(metadata.st_mode):
                    raise JournalPersistenceError(
                        "transaction journal must be a regular file"
                    )
                while True:
                    start = handle.tell()
                    line = handle.readline(self.max_record_bytes + 2)
                    if not line:
                        break
                    if len(line) > self.max_record_bytes + 1:
                        raise JournalPersistenceError(
                            "transaction journal record exceeds byte bound"
                        )
                    if not line.endswith(b"\n"):
                        extra = handle.read(1)
                        if extra:
                            raise JournalPersistenceError(
                                "transaction journal contains oversized record"
                            )
                        truncated_tail = True
                        break
                    body = line[:-1]
                    if not body:
                        raise JournalPersistenceError(
                            "transaction journal contains empty record"
                        )
                    try:
                        decoded = json.loads(body)
                    except (
                        UnicodeDecodeError,
                        json.JSONDecodeError,
                    ) as exc:
                        raise JournalPersistenceError(
                            "transaction journal contains invalid JSON"
                        ) from exc
                    event = self._event_from_mapping(decoded)
                    loaded.append(event)
                    if len(loaded) > self.max_events:
                        raise JournalPersistenceError(
                            "transaction journal exceeds event bound"
                        )
                    good_end = handle.tell()
                    if good_end <= start:
                        raise JournalPersistenceError(
                            "transaction journal reader made no progress"
                        )
        except OSError as exc:
            raise JournalPersistenceError(
                "failed reading transaction journal"
            ) from exc

        self._events = loaded
        if not self.verify():
            self._events = []
            raise JournalPersistenceError(
                "transaction journal hash-chain verification failed"
            )
        if truncated_tail:
            try:
                flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(self.storage_path, flags)
                with os.fdopen(fd, "r+b") as handle:
                    handle.truncate(good_end)
                    handle.flush()
                    if self.fsync:
                        os.fsync(handle.fileno())
            except OSError as exc:
                self._events = []
                raise JournalPersistenceError(
                    "failed repairing truncated journal tail"
                ) from exc
            self._recovered_truncated_tail = True

    def _persist(self, event: JournalEvent) -> None:
        if self.storage_path is None:
            return
        payload = canonical_json(event.to_dict()) + b"\n"
        if len(payload) > self.max_record_bytes:
            raise JournalPersistenceError(
                "transaction journal event exceeds record byte bound"
            )
        try:
            self._require_parent_directory()
            flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_APPEND
                | getattr(os, "O_NOFOLLOW", 0)
            )
            fd = os.open(self.storage_path, flags, 0o600)
            try:
                metadata = os.fstat(fd)
                if not stat.S_ISREG(metadata.st_mode):
                    raise JournalPersistenceError(
                        "transaction journal must be a regular file"
                    )
                offset = 0
                while offset < len(payload):
                    written = os.write(fd, payload[offset:])
                    if written <= 0:
                        raise JournalPersistenceError(
                            "transaction journal append made no progress"
                        )
                    offset += written
                if self.fsync:
                    os.fsync(fd)
            finally:
                os.close(fd)
        except JournalPersistenceError:
            raise
        except OSError as exc:
            raise JournalPersistenceError(
                "failed appending transaction journal"
            ) from exc

    def append(
        self,
        transaction_id: str,
        kind: str,
        payload: Mapping[str, Any] | None = None,
    ) -> JournalEvent:
        if not transaction_id or not kind:
            raise ValueError("transaction_id and kind are required")
        body = dict(payload or {})
        with self._lock:
            if len(self._events) >= self.max_events:
                raise RuntimeError("transaction journal capacity exhausted")
            sequence = len(self._events) + 1
            previous = (
                self._events[-1].event_hash
                if self._events
                else GENESIS
            )
            created_at = datetime.now(timezone.utc).isoformat()
            digest = self._hash(
                sequence,
                previous,
                transaction_id,
                kind,
                created_at,
                body,
            )
            event = JournalEvent(
                sequence,
                previous,
                digest,
                transaction_id,
                kind,
                created_at,
                body,
            )
            self._persist(event)
            self._events.append(event)
            return event

    def events(
        self,
        *,
        transaction_id: str | None = None,
        kind: str | None = None,
        after_sequence: int = 0,
    ) -> tuple[JournalEvent, ...]:
        with self._lock:
            values = tuple(
                event
                for event in self._events
                if event.sequence > after_sequence
            )
        if transaction_id is not None:
            values = tuple(
                event
                for event in values
                if event.transaction_id == transaction_id
            )
        if kind is not None:
            values = tuple(
                event for event in values if event.kind == kind
            )
        return values

    def verify(self) -> bool:
        with self._lock:
            previous = GENESIS
            for expected_sequence, event in enumerate(
                self._events,
                start=1,
            ):
                if (
                    event.sequence != expected_sequence
                    or event.previous_hash != previous
                ):
                    return False
                expected = self._hash(
                    event.sequence,
                    event.previous_hash,
                    event.transaction_id,
                    event.kind,
                    event.created_at,
                    event.payload,
                )
                if expected != event.event_hash:
                    return False
                previous = event.event_hash
            return True

    def root_hash(self) -> str:
        with self._lock:
            return (
                self._events[-1].event_hash
                if self._events
                else GENESIS
            )

    def transaction_state(self, transaction_id: str) -> str | None:
        events = self.events(transaction_id=transaction_id)
        return events[-1].kind if events else None

    def transaction_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(
                sorted(
                    {
                        event.transaction_id
                        for event in self._events
                    }
                )
            )

    def length(self) -> int:
        with self._lock:
            return len(self._events)
