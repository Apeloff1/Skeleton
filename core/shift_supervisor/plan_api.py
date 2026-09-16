from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .models import PlanItem
from .plan_store import InMemoryPlanStore
from .squads import SQUAD_SIZE, SquadCoordinator


class PlanReadAPI:
    """Read-only plan surface for Night/Idle workers and studio controllers."""

    def __init__(self, store: InMemoryPlanStore) -> None:
        self.store = store

    def pending_for_team(self, team: str) -> list[dict[str, Any]]:
        if team not in {"night", "idle"}:
            raise ValueError("team must be night or idle")
        items = [
            item
            for item in self.store.snapshot_items()
            if item.target_team == team
            and item.status in {"queued", "assigned", "working", "blocked"}
        ]
        items.sort(key=lambda item: (-item.priority, item.created_at))
        return [self._payload(item) for item in items]

    @staticmethod
    def _payload(item: PlanItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "priority": item.priority,
            "status": item.status,
            "owner": item.owner,
            "dependencies": list(item.dependencies),
            "research_refs": list(item.research_refs),
            "expected_output": item.expected_output,
            "validation": list(item.validation),
            "metadata": dict(item.metadata),
        }


class PlanQueueAPI:
    """Legacy queue for explicitly single-worker plan items.

    Autonomous four-agent work belongs to :class:`SquadPlanQueueAPI`. Legacy
    workers filter squad-stamped work before claiming so a high-priority squad
    item cannot starve lower-priority single-worker work.
    """

    def __init__(
        self,
        store: InMemoryPlanStore,
        *,
        overtime_soft_limit_minutes: int = 120,
    ) -> None:
        self.store = store
        self.overtime_soft_limit_minutes = overtime_soft_limit_minutes

    def claim_next(self, worker_id: str) -> dict[str, Any] | None:
        item = self._claim_next_legacy_item(worker_id)
        return PlanReadAPI._payload(item) if item is not None else None

    def _claim_next_legacy_item(self, worker_id: str) -> PlanItem | None:
        """Atomically claim the highest-priority non-squad task for a worker."""
        with self.store._lock:  # noqa: SLF001
            worker = self.store._workers.get(worker_id)  # noqa: SLF001
            if worker is None:
                raise KeyError(worker_id)
            if worker.status in {"offline", "blocked"}:
                return None
            if worker.current_task_id:
                return None
            overtime_limit = max(0, int(self.overtime_soft_limit_minutes))
            if (
                worker.overtime_minutes > 0
                if overtime_limit == 0
                else worker.overtime_minutes >= overtime_limit
            ):
                return None

            active_owned = any(
                item.owner == worker_id
                and item.status in {"assigned", "working", "blocked"}
                for item in self.store._items.values()  # noqa: SLF001
            )
            if active_owned:
                return None

            eligible = [
                item
                for item in self.store._items.values()  # noqa: SLF001
                if item.target_team == worker.team
                and item.status == "queued"
                and item.owner is None
                and not self._is_squad_item(item)
                and self.store._dependencies_satisfied(item)  # noqa: SLF001
            ]
            if not eligible:
                return None

            eligible.sort(key=lambda item: (-item.priority, item.created_at, item.id))
            item = eligible[0]
            now = datetime.now(timezone.utc)
            item.owner = worker_id
            item.status = "assigned"
            item.updated_at = now
            self.store._items[item.id] = replace(item)  # noqa: SLF001

            worker.current_task_id = item.id
            worker.status = "working"
            worker.last_heartbeat_at = now
            self.store._workers[worker_id] = replace(worker)  # noqa: SLF001
            return replace(item)

    @staticmethod
    def _is_squad_item(item: PlanItem) -> bool:
        if "squad_size" not in item.metadata:
            return False
        # Any explicit squad stamp is reserved for the squad runtime. Only the
        # canonical size is executable there; unsupported or malformed values
        # remain queued instead of leaking into legacy single-worker ownership.
        return True

    def complete(self, worker_id: str, item_id: str) -> dict[str, Any]:
        return PlanReadAPI._payload(
            self.store.finish_claim(worker_id, item_id, outcome="done")
        )

    def reject(self, worker_id: str, item_id: str) -> dict[str, Any]:
        return PlanReadAPI._payload(
            self.store.finish_claim(worker_id, item_id, outcome="rejected")
        )

    def release(self, worker_id: str, item_id: str) -> dict[str, Any]:
        """Return unfinished single-worker work to the shared queue."""
        return PlanReadAPI._payload(
            self.store.finish_claim(worker_id, item_id, outcome="queued")
        )


class SquadPlanQueueAPI:
    """Worker-facing four-agent queue for canonical anti-swarm execution."""

    def __init__(
        self,
        store: InMemoryPlanStore,
        *,
        overtime_soft_limit_minutes: int = 120,
        default_lease_minutes: int = 45,
    ) -> None:
        self.coordinator = SquadCoordinator(
            store,
            overtime_soft_limit_minutes=overtime_soft_limit_minutes,
            default_lease_minutes=default_lease_minutes,
        )

    def safe_capacity(self, team: str) -> int:
        self.recover_invalid_leases()
        # Capacity is used by the planner before new claims are attempted. Make
        # lease expiry visible here too, otherwise valid-but-expired leases can
        # strand four workers and make the planner incorrectly report zero
        # capacity until some later claim or explicit reclamation happens.
        self.coordinator.reclaim_expired()
        return self.coordinator.safe_capacity(team)

    def claim_next(
        self,
        team: str,
        *,
        plan_generation: str,
        worker_ids: Sequence[str] | None = None,
    ) -> dict[str, Any] | None:
        self.recover_invalid_leases()
        lease = self.coordinator.claim_next(
            team,
            plan_generation=plan_generation,
            worker_ids=worker_ids,
        )
        return lease.to_dict() if lease is not None else None

    def renew(
        self,
        squad_id: str,
        task_id: str,
        *,
        minutes: int | None = None,
    ) -> dict[str, Any]:
        return self.coordinator.renew(
            squad_id,
            task_id,
            minutes=minutes,
        ).to_dict()

    def complete(
        self,
        squad_id: str,
        task_id: str,
        *,
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        return PlanReadAPI._payload(
            self.coordinator.finish(
                squad_id,
                task_id,
                outcome="done",
                evidence=evidence,
            )
        )

    def reject(
        self,
        squad_id: str,
        task_id: str,
        *,
        evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return PlanReadAPI._payload(
            self.coordinator.finish(
                squad_id,
                task_id,
                outcome="rejected",
                evidence=evidence,
            )
        )

    def release(
        self,
        squad_id: str,
        task_id: str,
        *,
        evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return PlanReadAPI._payload(
            self.coordinator.finish(
                squad_id,
                task_id,
                outcome="queued",
                evidence=evidence,
            )
        )

    def revoke(
        self,
        squad_id: str,
        task_id: str,
        *,
        reason: str = "",
        requeue: bool = True,
    ) -> dict[str, Any]:
        """Immediately revoke one squad lease and return its worker capacity.

        Revocation is a control-plane mutation, so it does not rely on the
        worker-side finish path. The lease is archived before ownership is
        removed, all four members are released atomically, and a requeued task
        can receive a fresh lease generation instead of remaining poisoned by a
        stale ``lease_revoked`` flag.
        """
        coordinator = self.coordinator
        store = coordinator.store
        moment = datetime.now(timezone.utc)
        with store._lock:  # noqa: SLF001
            item = coordinator._require_owned_item_locked(squad_id, task_id)  # noqa: SLF001
            lease = coordinator._lease_from_item(item)  # noqa: SLF001
            history = coordinator._lease_history(item)  # noqa: SLF001
            record: dict[str, Any] = {
                **lease.to_dict(),
                "finished_at": moment.isoformat(),
                "outcome": "lease_revoked",
            }
            bounded_reason = str(reason).strip()[:2_000]
            if bounded_reason:
                record["reason"] = bounded_reason
            history.append(record)

            meta = dict(item.metadata)
            meta["squad_lease_history"] = history[-16:]
            meta["lease_revocation_count"] = coordinator._nonnegative_int(  # noqa: SLF001
                meta.get("lease_revocation_count")
            ) + 1
            meta["last_squad_outcome"] = "lease_revoked"
            meta.pop("squad_lease", None)
            meta.pop("lease_revoked", None)
            item.metadata = meta
            item.owner = None
            item.status = "queued" if requeue else "rejected"
            item.updated_at = moment
            store._items[item.id] = replace(item)  # noqa: SLF001
            coordinator._release_members_locked(lease, moment)  # noqa: SLF001
            return PlanReadAPI._payload(replace(item))

    def recover_invalid_leases(self) -> list[str]:
        """Fail closed but recover capacity from malformed durable squad leases.

        A corrupt or partially persisted lease must not leave an active task and
        four workers permanently wedged. Invalid active squad leases are
        archived as recovery events, their workers are released, and the task
        is returned to the canonical queue for a fresh lease generation.
        """
        coordinator = self.coordinator
        store = coordinator.store
        moment = datetime.now(timezone.utc)
        recovered: list[str] = []
        with store._lock:  # noqa: SLF001
            for item in list(store._items.values()):  # noqa: SLF001
                if item.status not in {"assigned", "working", "blocked"}:
                    continue
                owner = str(item.owner or "")
                if not owner.startswith("squad-"):
                    continue
                try:
                    coordinator._lease_from_item(item)  # noqa: SLF001
                    continue
                except ValueError as exc:
                    error = str(exc)[:500]

                history = coordinator._lease_history(item)  # noqa: SLF001
                history.append(
                    {
                        "squad_id": owner,
                        "task_id": item.id,
                        "team": item.target_team,
                        "finished_at": moment.isoformat(),
                        "outcome": "invalid_lease_recovered",
                        "error": error,
                    }
                )
                meta = dict(item.metadata)
                meta["squad_lease_history"] = history[-16:]
                meta["invalid_lease_recovery_count"] = coordinator._nonnegative_int(  # noqa: SLF001
                    meta.get("invalid_lease_recovery_count")
                ) + 1
                meta["last_squad_outcome"] = "invalid_lease_recovered"
                meta.pop("squad_lease", None)
                meta.pop("lease_revoked", None)
                item.metadata = meta
                item.owner = None
                item.status = "queued"
                item.updated_at = moment
                store._items[item.id] = replace(item)  # noqa: SLF001

                for worker_id, worker in list(store._workers.items()):  # noqa: SLF001
                    current_squad = str(worker.metadata.get("current_squad_id", ""))
                    owns_recovered_task = worker.current_task_id == item.id
                    orphaned_in_recovered_squad = (
                        worker.current_task_id is None and current_squad == owner
                    )
                    if not owns_recovered_task and not orphaned_in_recovered_squad:
                        continue
                    worker.current_task_id = None
                    if worker.status != "offline":
                        worker.status = "idle"
                    worker.last_heartbeat_at = moment
                    worker_meta = dict(worker.metadata)
                    worker_meta.pop("current_squad_id", None)
                    worker_meta.pop("current_squad_role", None)
                    worker.metadata = worker_meta
                    store._workers[worker_id] = replace(worker)  # noqa: SLF001
                recovered.append(item.id)
        return recovered

    def reclaim_expired(self) -> list[str]:
        self.recover_invalid_leases()
        return self.coordinator.reclaim_expired()
