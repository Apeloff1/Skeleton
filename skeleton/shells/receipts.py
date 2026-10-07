"""Execution receipts and tamper-evident receipt chains."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import threading
from types import MappingProxyType
from typing import Any, Mapping
import uuid

from skeleton.shells.provenance import canonical_json


@dataclass(frozen=True)
class ExecutionReceipt:
    command: str
    correlation_id: str
    fingerprint: str
    started_at: str
    finished_at: str
    duration_ms: float
    returncode: int | None
    ok: bool
    timed_out: bool
    output_limited: bool
    stdout_bytes: int
    stderr_bytes: int
    attempt: int = 1
    receipt_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
        if self.stdout_bytes < 0 or self.stderr_bytes < 0:
            raise ValueError("output byte counts must be non-negative")
        if self.attempt <= 0:
            raise ValueError("attempt must be positive")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "command": self.command,
            "correlation_id": self.correlation_id,
            "fingerprint": self.fingerprint,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "returncode": self.returncode,
            "ok": self.ok,
            "timed_out": self.timed_out,
            "output_limited": self.output_limited,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "attempt": self.attempt,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def now_failure(
        cls,
        *,
        command: str,
        correlation_id: str,
        fingerprint: str,
        returncode: int | None = None,
        timed_out: bool = False,
        output_limited: bool = False,
        attempt: int = 1,
    ) -> "ExecutionReceipt":
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            command=command,
            correlation_id=correlation_id,
            fingerprint=fingerprint,
            started_at=now,
            finished_at=now,
            duration_ms=0.0,
            returncode=returncode,
            ok=False,
            timed_out=timed_out,
            output_limited=output_limited,
            stdout_bytes=0,
            stderr_bytes=0,
            attempt=attempt,
        )


@dataclass(frozen=True)
class ChainedReceipt:
    sequence: int
    previous_hash: str
    receipt_hash: str
    receipt: ExecutionReceipt

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "previous_hash": self.previous_hash,
            "receipt_hash": self.receipt_hash,
            "receipt": self.receipt.to_dict(),
        }


class ReceiptChain:
    """Thread-safe SHA-256 chain over execution receipts."""

    GENESIS = "0" * 64

    def __init__(self, *, max_receipts: int = 100_000) -> None:
        if max_receipts <= 0:
            raise ValueError("max_receipts must be positive")
        self.max_receipts = max_receipts
        self._items: list[ChainedReceipt] = []
        self._lock = threading.RLock()

    @staticmethod
    def _hash(previous: str, sequence: int, receipt: ExecutionReceipt) -> str:
        payload = {
            "previous_hash": previous,
            "sequence": sequence,
            "receipt": receipt.to_dict(),
        }
        return hashlib.sha256(canonical_json(payload)).hexdigest()

    def append(self, receipt: ExecutionReceipt) -> ChainedReceipt:
        with self._lock:
            if len(self._items) >= self.max_receipts:
                raise RuntimeError("receipt chain capacity exhausted")
            sequence = len(self._items) + 1
            previous = self._items[-1].receipt_hash if self._items else self.GENESIS
            current = self._hash(previous, sequence, receipt)
            item = ChainedReceipt(sequence, previous, current, receipt)
            self._items.append(item)
            return item

    def snapshot(self) -> tuple[ChainedReceipt, ...]:
        with self._lock:
            return tuple(self._items)

    def verify(self) -> bool:
        with self._lock:
            previous = self.GENESIS
            for sequence, item in enumerate(self._items, start=1):
                if item.sequence != sequence or item.previous_hash != previous:
                    return False
                expected = self._hash(previous, sequence, item.receipt)
                if item.receipt_hash != expected:
                    return False
                previous = item.receipt_hash
            return True

    def root_hash(self) -> str:
        with self._lock:
            return self._items[-1].receipt_hash if self._items else self.GENESIS
