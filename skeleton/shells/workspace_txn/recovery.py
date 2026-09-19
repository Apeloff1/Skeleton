"""Crash/restart recovery inspection for transaction journals."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.workspace_txn.journal import JournalEvent, TransactionJournal
from skeleton.shells.workspace_txn.state_machine import TransactionStateMachine
from skeleton.shells.workspace_txn.types import WorkspaceTransactionState

_STATE_MACHINE = TransactionStateMachine()
_TERMINAL = frozenset(
    state.value
    for state in WorkspaceTransactionState
    if _STATE_MACHINE.terminal(state)
)


@dataclass(frozen=True)
class RecoveryCandidate:
    transaction_id: str
    last_state: str
    last_sequence: int
    needs_manual_review: bool
    safe_to_forget: bool
    reason: str
    backup_id: str = ""
    backup_digest: str = ""
    before_snapshot_digest: str = ""
    root_fingerprint: str = ""
    command_fingerprint: str = ""

    @property
    def evidence_complete(self) -> bool:
        return all(
            (
                self.backup_id,
                self.backup_digest,
                self.before_snapshot_digest,
                self.root_fingerprint,
                self.command_fingerprint,
            )
        )


class TransactionRecoveryInspector:
    def __init__(self, journal: TransactionJournal) -> None:
        self.journal = journal

    @staticmethod
    def _latest_text(events: list[JournalEvent], key: str) -> str:
        for event in reversed(events):
            value = event.payload.get(key)
            if isinstance(value, str) and value:
                return value
        return ""

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
                    backup_id=self._latest_text(events, "backup_id"),
                    backup_digest=self._latest_text(events, "backup_digest"),
                    before_snapshot_digest=self._latest_text(
                        events,
                        "before_snapshot_digest",
                    ),
                    root_fingerprint=self._latest_text(events, "root_fingerprint"),
                    command_fingerprint=self._latest_text(
                        events,
                        "command_fingerprint",
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
