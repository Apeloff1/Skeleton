"""Crash/restart recovery inspection for transaction journals."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.workspace_txn.backup import BackupError, ContentAddressedBackupStore
from skeleton.shells.workspace_txn.journal import JournalEvent, TransactionJournal
from skeleton.shells.workspace_txn.state_machine import TransactionStateMachine
from skeleton.shells.workspace_txn.types import BackupManifest, WorkspaceSnapshot, WorkspaceTransactionState

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


@dataclass(frozen=True)
class RecoveryEvidence:
    candidate: RecoveryCandidate
    manifest: BackupManifest
    before: WorkspaceSnapshot

    @property
    def verified(self) -> bool:
        return (
            self.candidate.evidence_complete
            and self.manifest.digest == self.candidate.backup_digest
            and self.before.digest == self.candidate.before_snapshot_digest
            and self.before.root_fingerprint == self.candidate.root_fingerprint
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
        if not self.journal.verify():
            raise RuntimeError(
                "transaction journal integrity verification failed"
            )
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

    def resolve_evidence(
        self,
        candidate: RecoveryCandidate,
        backup_store: ContentAddressedBackupStore,
    ) -> RecoveryEvidence:
        if not candidate.evidence_complete:
            raise BackupError(
                "recovery candidate lacks complete backup/snapshot evidence"
            )
        manifest = backup_store.load_manifest(
            candidate.backup_id,
            expected_digest=candidate.backup_digest,
            expected_root_fingerprint=candidate.root_fingerprint,
        )
        before = backup_store.reconstruct_snapshot(
            manifest,
            expected_digest=candidate.before_snapshot_digest,
        )
        evidence = RecoveryEvidence(candidate, manifest, before)
        if not evidence.verified:
            raise BackupError("resolved recovery evidence failed verification")
        return evidence

    def require_clean(self) -> None:
        risky = [candidate for candidate in self.candidates() if candidate.needs_manual_review]
        if risky:
            raise RuntimeError(
                f"{len(risky)} incomplete workspace transactions require recovery review"
            )
