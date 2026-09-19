"""Bounded searchable receipt history without raw command data."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import threading
from typing import Iterable

from skeleton.shells.receipts import ExecutionReceipt


@dataclass(frozen=True)
class HistoryQuery:
    command: str | None = None
    correlation_id: str | None = None
    ok: bool | None = None
    min_attempt: int | None = None
    limit: int = 100

    def __post_init__(self) -> None:
        if self.limit <= 0 or self.limit > 10_000:
            raise ValueError("history query limit is invalid")
        if self.min_attempt is not None and self.min_attempt <= 0:
            raise ValueError("min_attempt must be positive")


class ReceiptHistory:
    def __init__(self, *, max_receipts: int = 10_000) -> None:
        if max_receipts <= 0:
            raise ValueError("max_receipts must be positive")
        self.max_receipts = max_receipts
        self._receipts: deque[ExecutionReceipt] = deque(maxlen=max_receipts)
        self._lock = threading.RLock()

    def append(self, receipt: ExecutionReceipt) -> None:
        with self._lock:
            self._receipts.append(receipt)

    def extend(self, receipts: Iterable[ExecutionReceipt]) -> None:
        with self._lock:
            self._receipts.extend(receipts)

    def query(self, query: HistoryQuery | None = None) -> tuple[ExecutionReceipt, ...]:
        spec = query or HistoryQuery()
        with self._lock:
            matches: list[ExecutionReceipt] = []
            for receipt in reversed(self._receipts):
                if spec.command is not None and receipt.command != spec.command:
                    continue
                if spec.correlation_id is not None and receipt.correlation_id != spec.correlation_id:
                    continue
                if spec.ok is not None and receipt.ok is not spec.ok:
                    continue
                if spec.min_attempt is not None and receipt.attempt < spec.min_attempt:
                    continue
                matches.append(receipt)
                if len(matches) >= spec.limit:
                    break
            return tuple(matches)

    def count(self) -> int:
        with self._lock:
            return len(self._receipts)

    def commands(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted({receipt.command for receipt in self._receipts}))
