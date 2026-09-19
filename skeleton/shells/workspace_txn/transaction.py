"""High-level workspace transaction orchestration.

The only process execution call in this module is ShellExecutor.execute().
Everything else observes, constrains, journals, backs up, or restores workspace
state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Mapping
import uuid

from skeleton.shells.executor import ExecutionOutcome, ShellExecutor
from skeleton.shells.provenance import canonical_json, command_fingerprint
from skeleton.shells.retry import RetryPolicy
from skeleton.shells.runner import ShellCommand
from skeleton.shells.session import ShellSession
from skeleton.shells.workspace_txn.backup import ContentAddressedBackupStore
from skeleton.shells.workspace_txn.diff import WorkspaceDiffer
from skeleton.shells.workspace_txn.journal import TransactionJournal
from skeleton.shells.workspace_txn.lease import WorkspaceLease, WorkspaceLeaseRegistry
from skeleton.shells.workspace_txn.metrics import TransactionMetrics
from skeleton.shells.workspace_txn.policy import WorkspaceMutationPolicy, default_safe_policy
from skeleton.shells.workspace_txn.rollback import WorkspaceRollback
from skeleton.shells.workspace_txn.scanner import WorkspaceScanner
from skeleton.shells.workspace_txn.types import (
    TransactionReceipt,
    TransactionResult,
    WorkspaceTransactionState,
)


@dataclass(frozen=True)
class TransactionConfig:
    auto_rollback_on_execution_failure: bool = True
    auto_rollback_on_policy_rejection: bool = True
    require_clean_rollback: bool = True
    lease_ttl_seconds: float = 120.0

    def __post_init__(self) -> None:
        if isinstance(self.lease_ttl_seconds, bool) or self.lease_ttl_seconds <= 0:
            raise ValueError("lease_ttl_seconds must be positive")


class WorkspaceTransactionManager:
    def __init__(
        self,
        executor: ShellExecutor,
        *,
        scanner: WorkspaceScanner,
        backup_store: ContentAddressedBackupStore,
        policy: WorkspaceMutationPolicy | None = None,
        differ: WorkspaceDiffer | None = None,
        leases: WorkspaceLeaseRegistry | None = None,
        journal: TransactionJournal | None = None,
        metrics: TransactionMetrics | None = None,
        config: TransactionConfig | None = None,
    ) -> None:
        self.executor = executor
        self.scanner = scanner
        self.backup_store = backup_store
        self.policy = policy or default_safe_policy()
        self.differ = differ or WorkspaceDiffer()
        self.leases = leases or WorkspaceLeaseRegistry()
        self.journal = journal or TransactionJournal()
        self.metrics = metrics or TransactionMetrics()
        self.config = config or TransactionConfig()
        self.rollback_engine = WorkspaceRollback(scanner, backup_store)

    @staticmethod
    def _receipt_digest(receipt: TransactionReceipt) -> str:
        return hashlib.sha256(canonical_json(receipt.payload())).hexdigest()

    def _journal(
        self,
        transaction_id: str,
        state: WorkspaceTransactionState,
        **payload: object,
    ) -> None:
        self.journal.append(transaction_id, state.value, payload)

    def _build_receipt(
        self,
        *,
        transaction_id: str,
        correlation_id: str,
        state: WorkspaceTransactionState,
        command: ShellCommand,
        before_digest: str,
        after_digest: str,
        change_digest: str,
        policy_digest: str,
        policy_allowed: bool,
        execution: ExecutionOutcome,
        rollback,
        started_at: str,
        metadata: Mapping[str, str] | None,
    ) -> TransactionReceipt:
        base = TransactionReceipt(
            transaction_id=transaction_id,
            correlation_id=correlation_id,
            state=state,
            command_fingerprint=command_fingerprint(
                command.command,
                command.args,
                cwd=command.cwd,
                env_keys=tuple(command.env),
            ),
            before_snapshot_digest=before_digest,
            after_snapshot_digest=after_digest,
            change_set_digest=change_digest,
            policy_digest=policy_digest,
            policy_allowed=policy_allowed,
            execution_ok=execution.ok,
            rolled_back=rollback is not None,
            rollback_ok=None if rollback is None else rollback.ok,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            execution_receipt_ids=tuple(receipt.receipt_id for receipt in execution.receipts),
            metadata=dict(metadata or {}),
        )
        return TransactionReceipt(
            transaction_id=base.transaction_id,
            correlation_id=base.correlation_id,
            state=base.state,
            command_fingerprint=base.command_fingerprint,
            before_snapshot_digest=base.before_snapshot_digest,
            after_snapshot_digest=base.after_snapshot_digest,
            change_set_digest=base.change_set_digest,
            policy_digest=base.policy_digest,
            policy_allowed=base.policy_allowed,
            execution_ok=base.execution_ok,
            rolled_back=base.rolled_back,
            rollback_ok=base.rollback_ok,
            started_at=base.started_at,
            finished_at=base.finished_at,
            execution_receipt_ids=base.execution_receipt_ids,
            metadata=base.metadata,
            receipt_digest=self._receipt_digest(base),
        )

    def execute(
        self,
        root: Path | str,
        command: ShellCommand,
        *,
        principal: str = "workspace-transaction",
        correlation_id: str | None = None,
        retry: RetryPolicy | None = None,
        session: ShellSession | None = None,
        metadata: Mapping[str, str] | None = None,
        policy: WorkspaceMutationPolicy | None = None,
    ) -> TransactionResult:
        root_path = Path(root).expanduser().resolve(strict=True)
        transaction_id = uuid.uuid4().hex
        correlation = correlation_id or uuid.uuid4().hex
        started_at = datetime.now(timezone.utc).isoformat()
        effective_policy = self.policy if policy is None else policy
        workspace_id = hashlib.sha256(str(root_path).encode("utf-8")).hexdigest()
        lease: WorkspaceLease | None = None

        self._journal(
            transaction_id,
            WorkspaceTransactionState.CREATED,
            correlation_id=correlation,
        )
        try:
            lease = self.leases.acquire(
                workspace_id,
                principal,
                ttl_seconds=self.config.lease_ttl_seconds,
            )
            self._journal(
                transaction_id,
                WorkspaceTransactionState.LEASED,
                lease_id=lease.lease_id,
                generation=lease.generation,
            )

            self._journal(transaction_id, WorkspaceTransactionState.SNAPSHOTTING)
            before = self.scanner.scan(root_path)

            self._journal(transaction_id, WorkspaceTransactionState.BACKING_UP)
            backup = self.backup_store.create_manifest(root_path, before)
            if not self.backup_store.verify_manifest(backup):
                raise RuntimeError("pre-mutation backup failed verification")

            self.leases.require(lease)
            self._journal(transaction_id, WorkspaceTransactionState.EXECUTING)
            execution = self.executor.execute(
                command,
                retry=retry,
                session=session,
                correlation_id=correlation,
            )

            self.leases.require(lease)
            self._journal(transaction_id, WorkspaceTransactionState.REVIEWING)
            after = self.scanner.scan(root_path)
            changes = self.differ.diff(before, after)
            decision = effective_policy.evaluate(changes)

            should_rollback = (
                (
                    not execution.ok
                    and self.config.auto_rollback_on_execution_failure
                )
                or (
                    not decision.allowed
                    and self.config.auto_rollback_on_policy_rejection
                )
            )
            rollback = None
            state = WorkspaceTransactionState.ACCEPTED

            if should_rollback:
                self._journal(transaction_id, WorkspaceTransactionState.REJECTED)
                self._journal(transaction_id, WorkspaceTransactionState.ROLLING_BACK)
                rollback = self.rollback_engine.rollback(
                    root_path,
                    before,
                    changes,
                    backup,
                )
                state = (
                    WorkspaceTransactionState.ROLLED_BACK
                    if rollback.ok
                    else WorkspaceTransactionState.ROLLBACK_FAILED
                )
                self._journal(
                    transaction_id,
                    state,
                    rollback_ok=rollback.ok,
                )
            elif not execution.ok or not decision.allowed:
                state = WorkspaceTransactionState.REJECTED
                self._journal(transaction_id, state)
            else:
                self._journal(transaction_id, state)

            receipt = self._build_receipt(
                transaction_id=transaction_id,
                correlation_id=correlation,
                state=state,
                command=command,
                before_digest=before.digest,
                after_digest=after.digest,
                change_digest=changes.digest,
                policy_digest=decision.policy_digest,
                policy_allowed=decision.allowed,
                execution=execution,
                rollback=rollback,
                started_at=started_at,
                metadata=metadata,
            )
            result = TransactionResult(
                receipt=receipt,
                before=before,
                after=after,
                changes=changes,
                decision=decision,
                execution=execution,
                rollback=rollback,
                backup=backup,
            )
            self.metrics.record(result)
            if (
                rollback is not None
                and self.config.require_clean_rollback
                and not rollback.ok
            ):
                raise RuntimeError(
                    "workspace rollback did not restore pre-transaction state"
                )
            return result
        except Exception:
            self._journal(transaction_id, WorkspaceTransactionState.ABORTED)
            raise
        finally:
            if lease is not None:
                try:
                    self.leases.release(lease)
                except Exception:
                    pass

    def rollback_result(
        self,
        root: Path | str,
        result: TransactionResult,
    ):
        if result.backup is None:
            raise RuntimeError("transaction result has no backup manifest")
        return self.rollback_engine.rollback(
            root,
            result.before,
            result.changes,
            result.backup,
        )
