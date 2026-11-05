"""App-owned, journaled CPU/disk KV tier migration; no implicit retries."""
from __future__ import annotations

from dataclasses import dataclass
import os
import sqlite3
import stat

from skeleton.ai.runtime.inference.kv.manager import KVCacheManager
from skeleton.ai.runtime.inference.kv.live_tier_controller import (
    KVLiveTierController,
)
from skeleton.ai.runtime.inference.kv.migration_journal import (
    KVMigrationAnchor, KVMigrationJournal, KVJournaledTierController,
)
from skeleton.ai.runtime.inference.kv.pressure_tiering import (
    TierApplyReceipt, TierPlan, TierPressurePolicy,
)


def _require_private_durable_journal(connection: sqlite3.Connection) -> None:
    """Preflight only; caller must retain its own securely opened inode handle.

    An in-memory or shared SQLite journal cannot provide restart custody.
    This check does not itself establish a durable OS-level file lock or
    eliminate races with a malicious external process.
    """
    if type(connection) is not sqlite3.Connection or connection.in_transaction:
        raise ValueError("idle private SQLite journal connection required")
    try:
        databases = connection.execute("PRAGMA database_list").fetchall()
        synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        if (len(databases) != 1 or databases[0][1] != "main"
                or type(databases[0][2]) is not str or not databases[0][2]
                or type(synchronous) is not int or synchronous < 2
                or type(mode) is not str or mode.lower() in ("off", "memory")):
            raise ValueError("durable file-backed SQLite journal required")
        info = os.stat(databases[0][2], follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("untrusted journal inode")
        # Windows needs an independently verified ACL/handle adapter. Do not
        # pretend POSIX mode checks establish Windows filesystem custody.
        if os.name != "posix":
            raise ValueError("platform-specific journal ACL attestation required")
        if (info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError("private journal owner or mode invalid")
    except (OSError, sqlite3.Error, IndexError, TypeError) as exc:
        raise ValueError("private journal file verification failed") from exc


@dataclass(frozen=True, slots=True)
class OfflineKVMigrationStatus:
    schema: str
    plan_digest: str
    planned_moves: int
    moved: int
    rejected: int
    simulated: bool
    gpu_device_qualified: bool = False


class OfflineKVPageTierService:
    """Trusted app seam for bounded, write-ahead KV tier movement.

    The application supplies an exclusive, securely opened SQLite connection,
    separately provisioned journal key and an authorized KVStorageAdapter.
    This service does not provision keys, migrate model weights, or infer
    GPU/M-chip memory availability from host RAM.
    """

    def __init__(
        self, controller: KVLiveTierController,
        journal: KVMigrationJournal, *, simulated: bool = False,
    ) -> None:
        if not isinstance(controller, KVLiveTierController):
            raise ValueError("canonical live KV controller required")
        if not isinstance(journal, KVMigrationJournal):
            raise ValueError("canonical KV migration journal required")
        if type(simulated) is not bool or controller._simulated != simulated:
            raise ValueError("simulation provenance must match controller")
        self._service = KVJournaledTierController(controller, journal)
        self._simulated = simulated

    @classmethod
    def from_trusted_handles(
        cls, *, manager: KVCacheManager, connection: sqlite3.Connection,
        session_id: str, journal_key: bytes, storage_path: str,
        anchor: KVMigrationAnchor,
        policy: TierPressurePolicy | None = None,
    ) -> "OfflineKVPageTierService":
        """Production bootstrap: canonical live OS probe, no injected sensors."""
        _require_private_durable_journal(connection)
        controller = KVLiveTierController(
            manager, storage_path=storage_path, policy=policy,
        )
        journal = KVMigrationJournal(
            connection, session_id=session_id, journal_key=journal_key,
            anchor=anchor,
        )
        return cls(controller, journal)

    def bootstrap_new_journal_anchor(self) -> None:
        """Explicit first-install action, never called automatically on restart."""
        if self._simulated:
            raise ValueError("simulated journal is not a production rollback anchor")
        self._service._journal.bootstrap_anchor()

    def verified_journal_status(self) -> dict[str, int | str | bool]:
        """Read authenticated history; never treat a receipt as GPU evidence."""
        inventory = self._service._journal.verified_inventory()
        return {
            **inventory,
            "simulated": self._simulated,
            "gpu_device_qualified": False,
        }

    def plan_live(self) -> tuple[TierPlan, OfflineKVMigrationStatus]:
        plan, observation = self._service.plan_live()
        if observation.gpu_device_qualified:
            raise ValueError("unqualified GPU migration evidence")
        return plan, OfflineKVMigrationStatus(
            schema="skeleton.app.offline-kv-migration.v1",
            plan_digest=plan.digest,
            planned_moves=len(plan.moves),
            moved=0,
            rejected=0,
            simulated=self._simulated,
        )

    def apply_once(self, plan: TierPlan) -> OfflineKVMigrationStatus:
        """One attempt only; any rejection leaves a RUNNING journal hold."""
        receipt: TierApplyReceipt = self._service.apply_once(plan)
        return OfflineKVMigrationStatus(
            schema="skeleton.app.offline-kv-migration.v1",
            plan_digest=plan.digest,
            planned_moves=len(plan.moves),
            moved=len(receipt.moved),
            rejected=len(receipt.rejected),
            simulated=self._simulated,
        )


__all__ = ["OfflineKVPageTierService", "OfflineKVMigrationStatus"]
