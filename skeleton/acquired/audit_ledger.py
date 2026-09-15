"""Tamper-evident append-only audit ledger mined from Zaibatsu Gate.

The source middleware used a hash-chained WORM log as a fail-closed edge
control.  This port keeps the useful invariant while removing ASP.NET
coupling and tightening the durability/validation surface for Skeleton.

Properties:
- deterministic SHA-256 chaining over canonical JSON payloads
- strict sequence and previous-hash verification on load
- bounded text fields and line size
- append + flush + fsync before acknowledgement
- process-local serialization for concurrent writers
- optional EventBus publication after durable append

This is tamper-evident, not a substitute for filesystem/object-lock WORM
storage.  Deployments needing regulatory immutability should place the file
on storage that enforces append-only retention independently of the process.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from skeleton.kernel.events import EventBus

GENESIS_HASH = "GENESIS"
DEFAULT_MAX_FIELD_CHARS = 4096
DEFAULT_MAX_LINE_BYTES = 32 * 1024


class AuditChainError(RuntimeError):
    """Raised when an existing ledger cannot be verified safely."""


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    timestamp: float
    kind: str
    seal: str
    principal: str
    route: str
    detail: str
    prev_hash: str
    hash: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TamperEvidentAuditLog:
    """Small, dependency-free, hash-chained JSONL audit ledger."""

    def __init__(
        self,
        path: str | Path,
        *,
        bus: Optional[EventBus] = None,
        max_field_chars: int = DEFAULT_MAX_FIELD_CHARS,
        max_line_bytes: int = DEFAULT_MAX_LINE_BYTES,
        verify_on_open: bool = True,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.bus = bus
        self.max_field_chars = self._positive_int(max_field_chars, "max_field_chars")
        self.max_line_bytes = self._positive_int(max_line_bytes, "max_line_bytes")
        self._lock = threading.RLock()
        self._latest: Optional[AuditEntry] = None
        self._seq = 0
        if verify_on_open and self.path.exists():
            self.verify()

    @staticmethod
    def _positive_int(value: int, name: str) -> int:
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
        return value

    def _bounded(self, value: Any, field: str) -> str:
        text = str(value)
        if len(text) > self.max_field_chars:
            raise ValueError(f"{field} exceeds {self.max_field_chars} characters")
        return text

    @staticmethod
    def _payload(entry: AuditEntry) -> Dict[str, Any]:
        return {
            "seq": entry.seq,
            "timestamp": entry.timestamp,
            "kind": entry.kind,
            "seal": entry.seal,
            "principal": entry.principal,
            "route": entry.route,
            "detail": entry.detail,
            "prev_hash": entry.prev_hash,
        }

    @classmethod
    def compute_hash(cls, entry: AuditEntry) -> str:
        payload = json.dumps(
            cls._payload(entry),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def _from_mapping(cls, data: Dict[str, Any]) -> AuditEntry:
        required = {
            "seq",
            "timestamp",
            "kind",
            "seal",
            "principal",
            "route",
            "detail",
            "prev_hash",
            "hash",
        }
        if set(data) != required:
            missing = sorted(required - set(data))
            extra = sorted(set(data) - required)
            raise AuditChainError(f"invalid audit entry fields; missing={missing}, extra={extra}")
        if type(data["seq"]) is not int or data["seq"] <= 0:
            raise AuditChainError("audit sequence must be a positive integer")
        timestamp = data["timestamp"]
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
            raise AuditChainError("audit timestamp must be numeric")
        return AuditEntry(
            seq=data["seq"],
            timestamp=float(timestamp),
            kind=str(data["kind"]),
            seal=str(data["seal"]),
            principal=str(data["principal"]),
            route=str(data["route"]),
            detail=str(data["detail"]),
            prev_hash=str(data["prev_hash"]),
            hash=str(data["hash"]),
        )

    def _encode(self, entry: AuditEntry) -> bytes:
        line = (
            json.dumps(
                entry.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        if len(line) > self.max_line_bytes:
            raise ValueError(f"audit entry exceeds {self.max_line_bytes} bytes")
        return line

    def append(
        self,
        kind: str,
        *,
        seal: str = "",
        principal: str = "",
        route: str = "",
        detail: str = "",
        timestamp: Optional[float] = None,
    ) -> AuditEntry:
        """Durably append one entry and return it only after fsync succeeds."""

        with self._lock:
            ts = time.time() if timestamp is None else float(timestamp)
            if not (ts >= 0.0 and ts < float("inf")):
                raise ValueError("timestamp must be finite and non-negative")
            draft = AuditEntry(
                seq=self._seq + 1,
                timestamp=ts,
                kind=self._bounded(kind, "kind"),
                seal=self._bounded(seal, "seal"),
                principal=self._bounded(principal, "principal"),
                route=self._bounded(route, "route"),
                detail=self._bounded(detail, "detail"),
                prev_hash=self._latest.hash if self._latest else GENESIS_HASH,
                hash="",
            )
            entry = AuditEntry(**{**draft.to_dict(), "hash": self.compute_hash(draft)})
            line = self._encode(entry)

            with self.path.open("ab", buffering=0) as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())

            self._latest = entry
            self._seq = entry.seq
            if self.bus:
                self.bus.emit(
                    "acquired.audit.appended",
                    {
                        "seq": entry.seq,
                        "kind": entry.kind,
                        "route": entry.route,
                        "hash": entry.hash,
                    },
                )
            return entry

    def entries(self) -> Iterable[AuditEntry]:
        """Yield verified entries without mutating the current chain head."""

        if not self.path.exists():
            return ()
        items = []
        with self.path.open("rb") as handle:
            for index, raw in enumerate(handle, start=1):
                if len(raw) > self.max_line_bytes:
                    raise AuditChainError(f"audit line {index} exceeds configured bound")
                if not raw.strip():
                    continue
                try:
                    data = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise AuditChainError(f"audit line {index} is unreadable") from exc
                if not isinstance(data, dict):
                    raise AuditChainError(f"audit line {index} is not an object")
                items.append(self._from_mapping(data))
        return tuple(items)

    def verify(self) -> Dict[str, Any]:
        """Verify the full chain and restore the trusted head.

        Verification is fail-closed: malformed JSON, sequence gaps, wrong
        predecessor hashes, oversized fields/lines, or content-hash changes all
        raise :class:`AuditChainError` before state is accepted.
        """

        with self._lock:
            previous = GENESIS_HASH
            expected_seq = 1
            latest: Optional[AuditEntry] = None
            count = 0
            for entry in self.entries():
                for name in ("kind", "seal", "principal", "route", "detail"):
                    if len(getattr(entry, name)) > self.max_field_chars:
                        raise AuditChainError(f"audit field {name} exceeds configured bound")
                if entry.seq != expected_seq:
                    raise AuditChainError(
                        f"audit sequence mismatch at {entry.seq}; expected {expected_seq}"
                    )
                if entry.prev_hash != previous:
                    raise AuditChainError(f"audit previous hash mismatch at seq {entry.seq}")
                if entry.hash != self.compute_hash(entry):
                    raise AuditChainError(f"audit content hash mismatch at seq {entry.seq}")
                previous = entry.hash
                latest = entry
                expected_seq += 1
                count += 1

            self._latest = latest
            self._seq = latest.seq if latest else 0
            result = {
                "valid": True,
                "entries": count,
                "head": latest.hash if latest else GENESIS_HASH,
                "sequence": self._seq,
            }
            if self.bus:
                self.bus.emit("acquired.audit.verified", result)
            return result

    @property
    def latest(self) -> Optional[AuditEntry]:
        return self._latest

    def stats(self) -> Dict[str, Any]:
        return {
            "entries": self._seq,
            "head": self._latest.hash if self._latest else GENESIS_HASH,
            "path": str(self.path),
        }


__all__ = [
    "AuditChainError",
    "AuditEntry",
    "GENESIS_HASH",
    "TamperEvidentAuditLog",
]
