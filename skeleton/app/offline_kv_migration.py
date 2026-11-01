"""App-owned, journaled CPU/disk KV tier migration; no implicit retries."""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3

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
