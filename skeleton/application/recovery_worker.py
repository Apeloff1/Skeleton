"""Recovery worker boundary for retry reconciliation.

Keeps queue consumption separate from command execution and retry policy.
"""

from __future__ import annotations

from dataclasses import dataclass

from .reconciliation_queue import ReconciliationQueue


@dataclass(frozen=True)
class RecoveryResult:
    processed: bool
    execution_id: str


class RecoveryWorker:
    """Bounded recovery consumer.

    The worker only consumes reconciliation records. It does not execute
    commands or decide retry policy.
    """

    def __init__(self, queue: ReconciliationQueue) -> None:
        self._queue = queue

    def process_next(self) -> RecoveryResult | None:
        item = self._queue.pop()
        if item is None:
            return None

        return RecoveryResult(
            processed=True,
            execution_id=item.execution_id,
        )
