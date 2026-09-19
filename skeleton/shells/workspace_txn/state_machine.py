"""Explicit workspace transaction state-machine validation."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.workspace_txn.types import WorkspaceTransactionState


_ALLOWED: dict[WorkspaceTransactionState, frozenset[WorkspaceTransactionState]] = {
    WorkspaceTransactionState.CREATED: frozenset(
        {WorkspaceTransactionState.LEASED, WorkspaceTransactionState.ABORTED}
    ),
    WorkspaceTransactionState.LEASED: frozenset(
        {WorkspaceTransactionState.SNAPSHOTTING, WorkspaceTransactionState.ABORTED}
    ),
    WorkspaceTransactionState.SNAPSHOTTING: frozenset(
        {WorkspaceTransactionState.BACKING_UP, WorkspaceTransactionState.ABORTED}
    ),
    WorkspaceTransactionState.BACKING_UP: frozenset(
        {WorkspaceTransactionState.EXECUTING, WorkspaceTransactionState.ABORTED}
    ),
    WorkspaceTransactionState.EXECUTING: frozenset(
        {WorkspaceTransactionState.REVIEWING, WorkspaceTransactionState.ABORTED}
    ),
    WorkspaceTransactionState.REVIEWING: frozenset(
        {
            WorkspaceTransactionState.ACCEPTED,
            WorkspaceTransactionState.REJECTED,
            WorkspaceTransactionState.ABORTED,
        }
    ),
    WorkspaceTransactionState.REJECTED: frozenset(
        {WorkspaceTransactionState.ROLLING_BACK, WorkspaceTransactionState.ABORTED}
    ),
    WorkspaceTransactionState.ROLLING_BACK: frozenset(
        {
            WorkspaceTransactionState.ROLLED_BACK,
            WorkspaceTransactionState.ROLLBACK_FAILED,
            WorkspaceTransactionState.ABORTED,
        }
    ),
    WorkspaceTransactionState.ACCEPTED: frozenset(),
    WorkspaceTransactionState.ROLLED_BACK: frozenset(),
    WorkspaceTransactionState.ROLLBACK_FAILED: frozenset(),
    WorkspaceTransactionState.ABORTED: frozenset(),
}


@dataclass(frozen=True)
class TransitionDecision:
    allowed: bool
    source: WorkspaceTransactionState
    target: WorkspaceTransactionState
    reason: str


class TransactionStateMachine:
    def allowed_targets(
        self,
        source: WorkspaceTransactionState,
    ) -> frozenset[WorkspaceTransactionState]:
        return _ALLOWED[source]

    def inspect(
        self,
        source: WorkspaceTransactionState,
        target: WorkspaceTransactionState,
    ) -> TransitionDecision:
        allowed = target in _ALLOWED[source]
        return TransitionDecision(
            allowed,
            source,
            target,
            "allowed transition" if allowed else "transition is not permitted",
        )

    def require(
        self,
        source: WorkspaceTransactionState,
        target: WorkspaceTransactionState,
    ) -> None:
        decision = self.inspect(source, target)
        if not decision.allowed:
            raise RuntimeError(
                f"invalid workspace transaction transition: {source.value} -> {target.value}"
            )

    def terminal(self, state: WorkspaceTransactionState) -> bool:
        return not _ALLOWED[state]
