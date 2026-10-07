"""Bounded transaction metrics."""

from __future__ import annotations

from dataclasses import dataclass
import threading

from skeleton.shells.workspace_txn.types import TransactionResult


@dataclass(frozen=True)
class TransactionMetricSnapshot:
    transactions: int
    accepted: int
    rejected: int
    rolled_back: int
    rollback_failures: int
    execution_failures: int
    changes: int
    bytes_added: int
    bytes_removed: int

    @property
    def acceptance_ratio(self) -> float:
        return 1.0 if self.transactions == 0 else self.accepted / self.transactions

    @property
    def rollback_ratio(self) -> float:
        return 0.0 if self.transactions == 0 else self.rolled_back / self.transactions


class TransactionMetrics:
    def __init__(self) -> None:
        self._values = {
            "transactions": 0,
            "accepted": 0,
            "rejected": 0,
            "rolled_back": 0,
            "rollback_failures": 0,
            "execution_failures": 0,
            "changes": 0,
            "bytes_added": 0,
            "bytes_removed": 0,
        }
        self._lock = threading.RLock()

    def record(self, result: TransactionResult) -> None:
        with self._lock:
            self._values["transactions"] += 1
            if result.accepted:
                self._values["accepted"] += 1
            if not result.decision.allowed:
                self._values["rejected"] += 1
            if result.receipt.rolled_back:
                self._values["rolled_back"] += 1
            if result.rollback is not None and not result.rollback.ok:
                self._values["rollback_failures"] += 1
            if not result.receipt.execution_ok:
                self._values["execution_failures"] += 1
            self._values["changes"] += result.changes.statistics.total_changes
            self._values["bytes_added"] += result.changes.statistics.bytes_added
            self._values["bytes_removed"] += result.changes.statistics.bytes_removed

    def snapshot(self) -> TransactionMetricSnapshot:
        with self._lock:
            return TransactionMetricSnapshot(**self._values)
