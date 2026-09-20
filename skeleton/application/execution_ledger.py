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

    def begin(self, command: str, correlation: str = "") -> ExecutionRecord:
        identity = sha256(f"{command}:{correlation}:{len(self._records)}".encode()).hexdigest()[:24]
        record = ExecutionRecord(
            execution_id=identity,
            command=command,
            status=ExecutionStatus.STARTED,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._records[identity] = record
        self._trim()
        return record

    def complete(self, execution_id: str, success: bool, evidence: Mapping[str, Any] | None = None) -> ExecutionRecord:
        current = self._records[execution_id]
        updated = ExecutionRecord(
            execution_id=current.execution_id,
            command=current.command,
            status=ExecutionStatus.SUCCEEDED if success else ExecutionStatus.FAILED,
            created_at=current.created_at,
            attempts=current.attempts,
            evidence=dict(evidence or {}),
        )
        self._records[execution_id] = updated
        return updated

    def get(self, execution_id: str) -> ExecutionRecord | None:
        return self._records.get(execution_id)

    def _trim(self) -> None:
        while len(self._records) > self._max_records:
            self._records.pop(next(iter(self._records)))
