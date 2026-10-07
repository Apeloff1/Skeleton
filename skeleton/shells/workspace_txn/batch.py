"""Serial transaction batches with compensation policies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import uuid

from skeleton.shells.runner import ShellCommand
from skeleton.shells.workspace_txn.transaction import WorkspaceTransactionManager
from skeleton.shells.workspace_txn.types import RollbackReport, TransactionResult


@dataclass(frozen=True)
class BatchItem:
    command: ShellCommand
    name: str = ""
    continue_on_rejection: bool = False
    continue_on_execution_failure: bool = False


@dataclass(frozen=True)
class BatchResult:
    batch_id: str
    results: tuple[TransactionResult, ...]
    stopped_early: bool
    compensations: tuple[RollbackReport, ...] = ()

    @property
    def ok(self) -> bool:
        return (
            not self.stopped_early
            and all(result.accepted for result in self.results)
            and all(report.ok for report in self.compensations)
        )


@dataclass(frozen=True)
class BatchPolicy:
    compensate_accepted_on_failure: bool = False
    stop_on_rejection: bool = True
    stop_on_execution_failure: bool = True
    max_items: int = 256

    def __post_init__(self) -> None:
        if isinstance(self.max_items, bool) or not isinstance(self.max_items, int) or self.max_items <= 0:
            raise ValueError("max_items must be positive")


class WorkspaceTransactionBatch:
    def __init__(
        self,
        manager: WorkspaceTransactionManager,
        policy: BatchPolicy | None = None,
    ) -> None:
        self.manager = manager
        self.policy = policy or BatchPolicy()

    def execute(
        self,
        root: Path | str,
        items: Iterable[BatchItem],
        *,
        principal: str = "workspace-batch",
    ) -> BatchResult:
        values = tuple(items)
        if len(values) > self.policy.max_items:
            raise ValueError("workspace transaction batch exceeds item bound")
        batch_id = uuid.uuid4().hex
        results: list[TransactionResult] = []
        stopped = False
        for index, item in enumerate(values):
            result = self.manager.execute(
                root,
                item.command,
                principal=principal,
                metadata={
                    "batch_id": batch_id,
                    "batch_index": str(index),
                    "batch_name": item.name,
                },
            )
            results.append(result)
            if (
                not result.receipt.execution_ok
                and self.policy.stop_on_execution_failure
                and not item.continue_on_execution_failure
            ):
                stopped = True
                break
            if (
                not result.decision.allowed
                and self.policy.stop_on_rejection
                and not item.continue_on_rejection
            ):
                stopped = True
                break

        compensations: list[RollbackReport] = []
        if stopped and self.policy.compensate_accepted_on_failure:
            for result in reversed(results):
                if result.accepted:
                    report = self.manager.rollback_result(root, result)
                    compensations.append(report)
                    if not report.ok:
                        break
        return BatchResult(
            batch_id,
            tuple(results),
            stopped,
            tuple(compensations),
        )
