"""Crash/restart recovery inspection for transaction journals."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.workspace_txn.journal import JournalEvent, TransactionJournal
from skeleton.shells.workspace_txn.types import WorkspaceTransactionState

_TERMINAL = {
    WorkspaceTransactionState.ACCEPTED.value,
    WorkspaceTransactionState.REJECTED.value,
    WorkspaceTransactionState.ROLLED_BACK.value,
    WorkspaceTransactionState.ROLLBACK_FAILED.value,
    WorkspaceTransactionState.ABORTED.value,
}


@dataclass(frozen=True)
class RecoveryCandidate:
    transaction_id: str
    last_state: str
    last_sequence: int
    needs_manual_review: bool
    safe_to_forget: bool
    reason: str


class TransactionRecoveryInspector:
    def __init__(self, journal: TransactionJournal) -> None:
        self.journal = journal

    def candidates(self) -> tuple[RecoveryCandidate, ...]:
        by_transaction: dict[str, list[JournalEvent]] = {}
        for event in self.journal.events():
            by_transaction.setdefault(event.transaction_id, []).append(event)
        result: list[RecoveryCandidate] = []
        for transaction_id, events in sorted(by_transaction.items()):
            last = events[-1]
            if last.kind in _TERMINAL:
                continue
            mutated_possible = any(
                event.kind
                in {
                    WorkspaceTransactionState.EXECUTING.value,
                    WorkspaceTransactionState.REVIEWING.value,
                    WorkspaceTransactionState.ROLLING_BACK.value,
                }
                for event in events
            )
            result.append(
                RecoveryCandidate(
                    transaction_id=transaction_id,
                    last_state=last.kind,
                    last_sequence=last.sequence,
                    needs_manual_review=mutated_possible,
                    safe_to_forget=not mutated_possible,
                    reason=(
                        "execution may have mutated workspace; compare snapshot and backup evidence"
                        if mutated_possible
                        else "transaction did not reach execution"
                    ),
                )
            )
        return tuple(result)

    def require_clean(self) -> None:
        risky = [candidate for candidate in self.candidates() if candidate.needs_manual_review]
        if risky:
            raise RuntimeError(
                f"{len(risky)} incomplete workspace transactions require recovery review"
            )
