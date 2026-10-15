"""Bounded execution lifecycle primitives for application commands.

This module is intentionally transport-neutral. Command handlers may use it to
record execution identity, outcomes, and retry decisions without embedding
scheduler policy into API/CLI adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Mapping


class ExecutionStatus(str, Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYABLE = "retryable"


@dataclass(frozen=True)
class ExecutionRecord:
    execution_id: str
    command: str
    status: ExecutionStatus
    created_at: str
    attempts: int = 1
    evidence: Mapping[str, Any] = field(default_factory=dict)


class ExecutionLedger:
    """In-memory bounded ledger primitive.

    Persistence and queue ownership remain outside this component. The goal is
    deterministic lifecycle tracking at the application boundary.
    """

    def __init__(self, max_records: int = 1024) -> None:
        self._max_records = max(1, int(max_records))
        self._records: dict[str, ExecutionRecord] = {}
        self._next_sequence = 0

    def begin(self, command: str, correlation: str = "") -> ExecutionRecord:
        # Never evict an in-flight execution just to admit a new one. Prefer
        # old terminal records; reject admission if every slot is still active.
        if len(self._records) >= self._max_records:
            terminal_id = next(
                (
                    identity
                    for identity, record in self._records.items()
                    if record.status is not ExecutionStatus.STARTED
                ),
                None,
            )
            if terminal_id is None:
                raise OverflowError("execution ledger is full of active work")
            del self._records[terminal_id]

        # Retention-based counts stop advancing once the ledger is full.
        # A monotonic sequence prevents fresh executions overwriting older IDs
        # when the bounded history trims its oldest completed records.
        sequence = self._next_sequence
        self._next_sequence += 1
        identity = sha256(f"{command}:{correlation}:{sequence}".encode()).hexdigest()[:24]
        record = ExecutionRecord(
            execution_id=identity,
            command=command,
            status=ExecutionStatus.STARTED,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._records[identity] = record
        return record

    def complete(
        self,
        execution_id: str,
        success: bool,
        evidence: Mapping[str, Any] | None = None,
        *,
        retryable: bool = False,
    ) -> ExecutionRecord:
        if not isinstance(success, bool):
            raise TypeError("success must be boolean")
        if not isinstance(retryable, bool):
            raise TypeError("retryable must be boolean")
        if success and retryable:
            raise ValueError("successful execution cannot be retryable")
        current = self._records[execution_id]
        status = (
            ExecutionStatus.SUCCEEDED
            if success
            else (
                ExecutionStatus.RETRYABLE
                if retryable
                else ExecutionStatus.FAILED
            )
        )
        updated = ExecutionRecord(
            execution_id=current.execution_id,
            command=current.command,
            status=status,
            created_at=current.created_at,
            attempts=current.attempts,
            evidence=dict(evidence or {}),
        )
        self._records[execution_id] = updated
        return updated

    def get(self, execution_id: str) -> ExecutionRecord | None:
        return self._records.get(execution_id)

    def snapshot(self) -> tuple[ExecutionRecord, ...]:
        """Return the bounded ledger in deterministic insertion order."""

        return tuple(self._records.values())
