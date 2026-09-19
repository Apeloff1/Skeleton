from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

from .models import PlanItem, WorkerState
from .plan_store import InMemoryPlanStore
from .policy import may_admit_worker

SQUAD_SIZE = 4
SQUAD_ROLES = ("researcher", "lead", "reviewer", "verifier")
LEASE_SCHEMA_VERSION = 1
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMPLETION_EVIDENCE = (
    "research_complete",
    "implementation_complete",
    "reviewer_approved",
    "verifier_approved",
)


@dataclass(frozen=True, slots=True)
class SquadLease:
    squad_id: str
    task_id: str
    team: str
    members: dict[str, str]
    conflict_domain: str
    plan_generation: str
    lease_generation: int
    started_at: datetime
    expires_at: datetime

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": LEASE_SCHEMA_VERSION,
            "squad_id": self.squad_id,
            "task_id": self.task_id,
            "team": self.team,
            "members": {role: self.members[role] for role in SQUAD_ROLES},
            "conflict_domain": self.conflict_domain,
            "plan_generation": self.plan_generation,
            "lease_generation": self.lease_generation,
            "started_at": self.started_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self._identity_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        payload = self._identity_payload()
        payload["fingerprint"] = self.fingerprint
        return payload


def safe_squad_capacity(
    workers: Iterable[WorkerState],
    team: str,
    *,
    overtime_soft_limit_minutes: int = 120,
) -> int:
    """Return safe four-person squad capacity for one team."""
    if team not in {"night", "idle"}:
        raise ValueError("team must be night or idle")
    eligible = sum(
        1
        for worker in workers
        if worker.team == team
        and may_admit_worker(
            worker=worker,
            overtime_soft_limit_minutes=overtime_soft_limit_minutes,
        ).allowed
    )
    return eligible // SQUAD_SIZE


class SquadCoordinator:
    """Atomic four-agent leasing over the canonical plan store.

    New claims must use the current plan generation when revision state exists.
    Once issued, a live lease survives later plan refreshes until completion,
    release, rejection, explicit revocation, or expiry.
    """

    def __init__(
        self,
        store: InMemoryPlanStore,
        *,
        overtime_soft_limit_minutes: int = 120,
        default_lease_minutes: int = 45,
    ) -> None:
        self.store = store
        self.overtime_soft_limit_minutes = self._policy_minutes(
            overtime_soft_limit_minutes,
            name="overtime_soft_limit_minutes",
            minimum=0,
            maximum=24 * 60,
        )
        self.default_lease_minutes = self._policy_minutes(
            default_lease_minutes,
            name="default_lease_minutes",
            minimum=5,
            maximum=240,
        )

    def safe_capacity(self, team: str) -> int:
        return safe_squad_capacity(
            self.store.snapshot_workers(),
            team,
            overtime_soft_limit_minutes=self.overtime_soft_limit_minutes,
        )

    def claim_next(
        self,
        team: str,
        *,
        plan_generation: str,
        worker_ids: Sequence[str] | None = None,
        lease_minutes: int | None = None,
        now: datetime | None = None,
    ) -> SquadLease | None:
        if team not in {"night", "idle"}:
            raise ValueError("team must be night or idle")
        generation = str(plan_generation).strip()
        if not generation:
            raise ValueError("plan_generation is required")
        moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        lease_for = (
            self.default_lease_minutes
            if lease_minutes is None
            else self._policy_minutes(
                lease_minutes,
                name="lease_minutes",
                minimum=5,
                maximum=240,
            )
        )

        with self.store._lock:  # noqa: SLF001
            self._reclaim_expired_locked(moment)
            self._require_current_generation_locked(generation)
            allowed_workers = set(worker_ids) if worker_ids is not None else None
            workers = self._eligible_workers_locked(team, allowed_workers)
            if len(workers) < SQUAD_SIZE:
                return None

            active_domains = self._active_conflict_domains_locked()
            items = [
                item
                for item in self.store._items.values()  # noqa: SLF001
                if item.target_team == team
                and item.status == "queued"
                and item.owner is None
                and self._is_squad_task(item)
                and self.store._dependencies_satisfied(item)  # noqa: SLF001
                and self._conflict_domain(item) not in active_domains
            ]
            if not items:
                return None
            items.sort(key=lambda item: (-item.priority, item.created_at, item.id))
            item = items[0]
            selected = self._select_role_members(workers)
            squad_id = f"squad-{uuid4()}"
            conflict_domain = self._conflict_domain(item)
            lease_generation = self._next_lease_generation(item)
            lease = SquadLease(
                squad_id=squad_id,
                task_id=item.id,
                team=team,
                members={role: worker.worker_id for role, worker in selected.items()},
                conflict_domain=conflict_domain,
                plan_generation=generation,
                lease_generation=lease_generation,
                started_at=moment,
                expires_at=moment + timedelta(minutes=lease_for),
            )

            item_meta = dict(item.metadata)
            item_meta.update(
                {
                    "squad_size": SQUAD_SIZE,
                    "squad_roles": list(SQUAD_ROLES),
                    "conflict_domain": conflict_domain,
                    "plan_generation": generation,
                    "lease_generation": lease_generation,
                    "squad_lease": lease.to_dict(),
                }
            )
            item.owner = squad_id
            item.status = "assigned"
            item.updated_at = moment
            item.metadata = item_meta
            self.store._items[item.id] = replace(item)  # noqa: SLF001

            for role, worker in selected.items():
                worker_meta = dict(worker.metadata)
                worker_meta.update(
                    {
                        "current_squad_id": squad_id,
                        "current_squad_role": role,
                        "squad_assignment_count": self._nonnegative_int(
                            worker_meta.get("squad_assignment_count")
                        )
                        + 1,
                    }
                )
                worker.current_task_id = item.id
                worker.status = "working"
                worker.last_heartbeat_at = moment
                worker.metadata = worker_meta
                self.store._workers[worker.worker_id] = replace(worker)  # noqa: SLF001
            return lease

    def renew(
        self,
        squad_id: str,
        task_id: str,
        *,
        minutes: int | None = None,
        now: datetime | None = None,
    ) -> SquadLease:
        moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        extend = (
            self.default_lease_minutes
            if minutes is None
            else self._policy_minutes(
                minutes,
                name="minutes",
                minimum=5,
                maximum=240,
            )
        )
        with self.store._lock:  # noqa: SLF001
            item = self._require_owned_item_locked(squad_id, task_id)
            lease = self._lease_from_item(item)
            self._require_live_lease(lease, moment)
            self._require_not_revoked(item)
            renewed = SquadLease(
                squad_id=lease.squad_id,
                task_id=lease.task_id,
                team=lease.team,
                members=dict(lease.members),
                conflict_domain=lease.conflict_domain,
                plan_generation=lease.plan_generation,
                lease_generation=lease.lease_generation,
                started_at=lease.started_at,
                expires_at=moment + timedelta(minutes=extend),
            )
            item.metadata = {**item.metadata, "squad_lease": renewed.to_dict()}
            item.updated_at = moment
            self.store._items[item.id] = replace(item)  # noqa: SLF001
            for worker_id in renewed.members.values():
                worker = self.store._workers.get(worker_id)  # noqa: SLF001
                if worker is not None and worker.current_task_id == task_id:
                    worker.last_heartbeat_at = moment
                    self.store._workers[worker_id] = replace(worker)  # noqa: SLF001
            return renewed

    def finish(
        self,
        squad_id: str,
        task_id: str,
        *,
        outcome: str,
        evidence: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> PlanItem:
        if outcome not in {"done", "rejected", "queued"}:
            raise ValueError("outcome must be done, rejected, or queued")
        proof = dict(evidence or {})
        if outcome == "done":
            missing = [key for key in _COMPLETION_EVIDENCE if proof.get(key) is not True]
            if missing:
                raise ValueError(f"completion evidence missing: {', '.join(missing)}")

        moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        with self.store._lock:  # noqa: SLF001
            item = self._require_owned_item_locked(squad_id, task_id)
            lease = self._lease_from_item(item)
            self._require_live_lease(lease, moment)
            self._require_not_revoked(item)
            history = self._lease_history(item)
            history.append(
                {
                    **lease.to_dict(),
                    "finished_at": moment.isoformat(),
                    "outcome": outcome,
                    "evidence": self._bounded_evidence(proof),
                }
            )
            meta = dict(item.metadata)
            meta["squad_lease_history"] = history[-16:]
            meta.pop("squad_lease", None)
            meta["last_squad_outcome"] = outcome
            if proof:
                meta["completion_evidence"] = self._bounded_evidence(proof)
            item.metadata = meta
            item.status = outcome  # type: ignore[assignment]
            item.updated_at = moment
            if outcome == "queued":
                item.owner = None
            self.store._items[item.id] = replace(item)  # noqa: SLF001
            self._release_members_locked(lease, moment)
            return replace(item)

    def reclaim_expired(self, *, now: datetime | None = None) -> list[str]:
        moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        with self.store._lock:  # noqa: SLF001
            return self._reclaim_expired_locked(moment)

    def _reclaim_expired_locked(self, now: datetime) -> list[str]:
        reclaimed: list[str] = []
        for item in list(self.store._items.values()):  # noqa: SLF001
            if item.status not in {"assigned", "working", "blocked"}:
                continue
            if not str(item.owner or "").startswith("squad-"):
                continue
            try:
                lease = self._lease_from_item(item)
            except ValueError:
                continue
            if lease.expires_at > now:
                continue
            history = self._lease_history(item)
            history.append(
                {
                    **lease.to_dict(),
                    "finished_at": now.isoformat(),
                    "outcome": "lease_expired",
                }
            )
            meta = dict(item.metadata)
            meta["squad_lease_history"] = history[-16:]
            meta["lease_expiry_count"] = self._nonnegative_int(
                meta.get("lease_expiry_count")
            ) + 1
            meta.pop("squad_lease", None)
            item.metadata = meta
            item.owner = None
            item.status = "queued"
            item.updated_at = now
            self.store._items[item.id] = replace(item)  # noqa: SLF001
            self._release_members_locked(lease, now)
            reclaimed.append(item.id)
        return reclaimed

    def _require_current_generation_locked(self, generation: str) -> None:
        revisions = self.store._revisions  # noqa: SLF001
        if not revisions:
            return
        current = revisions[-1].revision_id
        if generation != current:
            raise ValueError(f"stale plan_generation: expected {current!r}")

    @staticmethod
    def _require_live_lease(lease: SquadLease, now: datetime) -> None:
        if lease.expires_at <= now:
            raise PermissionError("squad lease expired; reclaim before further mutation")

    @staticmethod
    def _require_not_revoked(item: PlanItem) -> None:
        if item.metadata.get("lease_revoked") is True:
            raise PermissionError("squad lease was revoked by the control plane")

    @staticmethod
    def _is_squad_task(item: PlanItem) -> bool:
        try:
            return int(item.metadata.get("squad_size", 0)) == SQUAD_SIZE
        except (TypeError, ValueError):
            return False

    def _eligible_workers_locked(
        self, team: str, allowed_workers: set[str] | None
    ) -> list[WorkerState]:
        result: list[WorkerState] = []
        for worker in self.store._workers.values():  # noqa: SLF001
            if worker.team != team:
                continue
            if not may_admit_worker(
                worker=worker,
                overtime_soft_limit_minutes=self.overtime_soft_limit_minutes,
            ).allowed:
                continue
            if allowed_workers is not None and worker.worker_id not in allowed_workers:
                continue
            result.append(replace(worker))
        return result

    def _select_role_members(
        self, workers: Sequence[WorkerState]
    ) -> dict[str, WorkerState]:
        remaining = list(workers)
        selected: dict[str, WorkerState] = {}
        for role in SQUAD_ROLES:
            remaining.sort(key=lambda worker: self._worker_role_score(worker, role))
            selected[role] = remaining.pop(0)
        return selected

    @classmethod
    def _worker_role_score(
        cls, worker: WorkerState, role: str
    ) -> tuple[int, int, int, str]:
        preferred = worker.metadata.get("preferred_squad_roles", [])
        preferred_roles = (
            {str(value) for value in preferred} if isinstance(preferred, list) else set()
        )
        role_penalty = 0 if role in preferred_roles else 1
        return (
            role_penalty,
            cls._nonnegative_int(worker.metadata.get("squad_assignment_count")),
            worker.overtime_minutes,
            worker.worker_id,
        )

    def _active_conflict_domains_locked(self) -> set[str]:
        return {
            self._conflict_domain(item)
            for item in self.store._items.values()  # noqa: SLF001
            if item.status in {"assigned", "working", "blocked"}
            and str(item.owner or "").startswith("squad-")
        }

    @staticmethod
    def _conflict_domain(item: PlanItem) -> str:
        paths = item.metadata.get("relevant_paths", [])
        if isinstance(paths, list):
            for raw in paths:
                path = str(raw).strip().strip("/")
                if path:
                    return "/".join(path.split("/")[:2])[:300]
        explicit = str(item.metadata.get("conflict_domain", "")).strip()
        if explicit:
            return explicit[:300]
        return f"task:{item.id}"

    @staticmethod
    def _next_lease_generation(item: PlanItem) -> int:
        value = item.metadata.get("lease_generation")
        if value is None:
            return 1
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("invalid task lease generation")
        return value + 1

    @staticmethod
    def _policy_minutes(
        value: Any,
        *,
        name: str,
        minimum: int,
        maximum: int,
    ) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
        return max(minimum, min(value, maximum))

    def _require_owned_item_locked(self, squad_id: str, task_id: str) -> PlanItem:
        item = self.store._items.get(task_id)  # noqa: SLF001
        if item is None:
            raise KeyError(task_id)
        if item.owner != squad_id:
            raise PermissionError(f"{squad_id!r} does not own {task_id!r}")
        return item

    @classmethod
    def _lease_from_item(cls, item: PlanItem) -> SquadLease:
        raw = item.metadata.get("squad_lease")
        if not isinstance(raw, Mapping):
            raise ValueError("malformed squad lease: envelope missing")
        schema_version = raw.get("schema_version")
        if isinstance(schema_version, bool) or type(schema_version) is not int:
            raise ValueError("malformed squad lease: invalid schema version")
        if schema_version != LEASE_SCHEMA_VERSION:
            raise ValueError("malformed squad lease: unsupported schema version")

        fingerprint = raw.get("fingerprint")
        if not isinstance(fingerprint, str) or not _SHA256_RE.fullmatch(fingerprint):
            raise ValueError("malformed squad lease: fingerprint missing")

        members_raw = raw.get("members")
        if not isinstance(members_raw, Mapping):
            raise ValueError("malformed squad lease: members missing")
        if set(members_raw) != set(SQUAD_ROLES):
            raise ValueError("malformed squad lease: canonical roles required")
        members: dict[str, str] = {}
        for role in SQUAD_ROLES:
            worker_id = members_raw.get(role)
            if not isinstance(worker_id, str):
                raise ValueError("malformed squad lease: worker identity must be text")
            worker_id = worker_id.strip()
            if not worker_id or len(worker_id) > 500 or "\\x00" in worker_id:
                raise ValueError("malformed squad lease: invalid worker identity")
            members[role] = worker_id
        if len(set(members.values())) != SQUAD_SIZE:
            raise ValueError("malformed squad lease: four distinct workers required")

        generation = raw.get("lease_generation")
        if isinstance(generation, bool) or type(generation) is not int or generation < 1:
            raise ValueError("malformed squad lease: invalid lease generation")

        try:
            started = datetime.fromisoformat(str(raw["started_at"]).replace("Z", "+00:00"))
            expires = datetime.fromisoformat(str(raw["expires_at"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("malformed squad lease: invalid timestamp") from exc
        if started.tzinfo is None or started.utcoffset() is None:
            raise ValueError("malformed squad lease: start timestamp must be timezone-aware")
        if expires.tzinfo is None or expires.utcoffset() is None:
            raise ValueError("malformed squad lease: expiry timestamp must be timezone-aware")

        def require_text(name: str, *, maximum: int = 500) -> str:
            value = raw.get(name)
            if not isinstance(value, str):
                raise ValueError(f"malformed squad lease: {name} must be text")
            value = value.strip()
            if not value or len(value) > maximum or "\\x00" in value:
                raise ValueError(f"malformed squad lease: invalid {name}")
            return value

        lease = SquadLease(
            squad_id=require_text("squad_id"),
            task_id=require_text("task_id"),
            team=require_text("team", maximum=16),
            members=members,
            conflict_domain=require_text("conflict_domain"),
            plan_generation=require_text("plan_generation"),
            lease_generation=generation,
            started_at=started.astimezone(timezone.utc),
            expires_at=expires.astimezone(timezone.utc),
        )
        if lease.squad_id != item.owner:
            raise ValueError("malformed squad lease: owner mismatch")
        if lease.task_id != item.id:
            raise ValueError("malformed squad lease: task mismatch")
        if lease.team != item.target_team:
            raise ValueError("malformed squad lease: team mismatch")
        if lease.expires_at <= lease.started_at:
            raise ValueError("malformed squad lease: expiry must follow start")
        task_generation = item.metadata.get("lease_generation")
        if (
            isinstance(task_generation, bool)
            or type(task_generation) is not int
            or task_generation != lease.lease_generation
        ):
            raise ValueError("malformed squad lease: generation mismatch")
        if lease.fingerprint != fingerprint:
            raise ValueError("malformed squad lease: fingerprint mismatch")
        return lease

    def _release_members_locked(self, lease: SquadLease, now: datetime) -> None:
        for worker_id in lease.members.values():
            worker = self.store._workers.get(worker_id)  # noqa: SLF001
            if worker is None or worker.current_task_id != lease.task_id:
                continue
            worker.current_task_id = None
            if worker.status != "offline":
                worker.status = "idle"
            worker.last_heartbeat_at = now
            meta = dict(worker.metadata)
            meta.pop("current_squad_id", None)
            meta.pop("current_squad_role", None)
            worker.metadata = meta
            self.store._workers[worker_id] = replace(worker)  # noqa: SLF001

    @staticmethod
    def _lease_history(item: PlanItem) -> list[dict[str, Any]]:
        value = item.metadata.get("squad_lease_history", [])
        if not isinstance(value, list):
            return []
        return [dict(row) for row in value[-15:] if isinstance(row, Mapping)]

    @staticmethod
    def _bounded_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
        bounded: dict[str, Any] = {}
        for key, raw in list(value.items())[:32]:
            name = str(key)[:100]
            if isinstance(raw, bool) or raw is None or isinstance(raw, (int, float)):
                bounded[name] = raw
            elif isinstance(raw, str):
                bounded[name] = raw[:2_000]
            elif isinstance(raw, list):
                bounded[name] = [str(item)[:500] for item in raw[:20]]
            else:
                bounded[name] = str(raw)[:2_000]
        return bounded

    @staticmethod
    def _nonnegative_int(value: Any) -> int:
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return max(0, value)
        try:
            return max(0, int(value))
        except (TypeError, ValueError, OverflowError):
            return 0
