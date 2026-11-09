"""Bounded high-level execution history built from receipt metadata."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Iterable

from skeleton.shells.receipts import ExecutionReceipt


@dataclass(frozen=True)
class HistoryQuery:
    command: str | None = None
    correlation_id: str | None = None
    ok: bool | None = None
    timed_out: bool | None = None
    output_limited: bool | None = None


@dataclass(frozen=True)
class ExecutionHistorySummary:
    total: int
    succeeded: int
    failed: int
    timed_out: int
    output_limited: int
    commands: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "timed_out": self.timed_out,
            "output_limited": self.output_limited,
            "commands": dict(self.commands),
        }


class ExecutionHistory:
    def __init__(self, *, max_receipts: int = 100000) -> None:
        if max_receipts <= 0:
            raise ValueError("max_receipts must be positive")
        self.max_receipts = max_receipts
        self._items: list[ExecutionReceipt] = []
        self._ids: set[str] = set()
        self._lock = threading.RLock()

    def append(self, receipt: ExecutionReceipt) -> None:
        with self._lock:
            if receipt.receipt_id in self._ids:
                raise ValueError("duplicate execution receipt")
            self._items.append(receipt)
            self._ids.add(receipt.receipt_id)
            if len(self._items) > self.max_receipts:
                removed = self._items.pop(0)
                self._ids.discard(removed.receipt_id)

    def extend(self, receipts: Iterable[ExecutionReceipt]) -> None:
        for receipt in receipts:
            self.append(receipt)

    def query(self, query: HistoryQuery) -> tuple[ExecutionReceipt, ...]:
        with self._lock:
            result = []
            for item in self._items:
                if query.command is not None and item.command != query.command:
                    continue
                if query.correlation_id is not None and item.correlation_id != query.correlation_id:
                    continue
                if query.ok is not None and item.ok is not query.ok:
                    continue
                if query.timed_out is not None and item.timed_out is not query.timed_out:
                    continue
                if query.output_limited is not None and item.output_limited is not query.output_limited:
                    continue
                result.append(item)
            return tuple(result)

    def summary(self) -> ExecutionHistorySummary:
        with self._lock:
            commands: dict[str, int] = {}
            for item in self._items:
                commands[item.command] = commands.get(item.command, 0) + 1
            return ExecutionHistorySummary(
                total=len(self._items),
                succeeded=sum(item.ok for item in self._items),
                failed=sum(not item.ok for item in self._items),
                timed_out=sum(item.timed_out for item in self._items),
                output_limited=sum(item.output_limited for item in self._items),
                commands=dict(sorted(commands.items())),
            )

    def snapshot(self) -> tuple[ExecutionReceipt, ...]:
        with self._lock:
            return tuple(self._items)
