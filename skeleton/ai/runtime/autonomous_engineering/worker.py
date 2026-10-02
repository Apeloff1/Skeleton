"""Durable long-horizon P3 autonomous-worker control envelope."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Iterable


class WorkerControlError(RuntimeError):
    pass


def _id(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be text")
    text = value.strip()
    if not text or len(text) > maximum:
        raise ValueError(f"{field} must be non-empty bounded text")
    return text


def _sha(value: object, field: str) -> str:
    text = _id(value, field, maximum=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{field} must be lowercase sha256")
    return text


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _money(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise TypeError(f"{field} must be numeric")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be finite decimal") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field} must be finite non-negative decimal")
    return amount.quantize(Decimal("0.000001"))


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class WorkerBudget:
    max_steps: int
    max_actions: int
    max_cost: Decimal

    def __post_init__(self) -> None:
        for field, maximum in (("max_steps", 100000), ("max_actions", 10000)):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                raise ValueError(f"{field} must be integer in [1,{maximum}]")
        object.__setattr__(self, "max_cost", _money(self.max_cost, "max_cost"))


@dataclass(frozen=True, slots=True)
class WorkerCheckpoint:
    run_id: str
    objective: str
    repository_fingerprint: str
    authority_digest: str
    status: str
    revision: int
    steps_used: int
    actions_used: int
    cost_used: Decimal
    deadline_at: datetime
    active_conflict_domains: tuple[str, ...]
    last_evidence_refs: tuple[str, ...]
    updated_at: datetime
    checkpoint_digest: str

    def __post_init__(self) -> None:
        for field in ("run_id", "objective"):
            object.__setattr__(self, field, _id(getattr(self, field), field, maximum=4096))
        object.__setattr__(
            self,
            "repository_fingerprint",
            _sha(self.repository_fingerprint, "repository_fingerprint"),
        )
        object.__setattr__(
            self,
            "authority_digest",
            _sha(self.authority_digest, "authority_digest"),
        )
        if self.status not in {"active", "interrupted", "halted", "completed", "failed"}:
            raise ValueError("unsupported worker status")
        for field in ("revision", "steps_used", "actions_used"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field} must be non-negative integer")
        object.__setattr__(self, "cost_used", _money(self.cost_used, "cost_used"))
        object.__setattr__(self, "deadline_at", _utc(self.deadline_at, "deadline_at"))
        object.__setattr__(self, "updated_at", _utc(self.updated_at, "updated_at"))
        domains = tuple(sorted({_id(item, "conflict_domain") for item in self.active_conflict_domains}))
        object.__setattr__(self, "active_conflict_domains", domains)
        refs = tuple(sorted({_id(item, "evidence_ref", maximum=1024) for item in self.last_evidence_refs}))
        object.__setattr__(self, "last_evidence_refs", refs)
        _sha(self.checkpoint_digest, "checkpoint_digest")


class WorkerCheckpointStore:
    """SQLite durable state for interruption/reopen/recovery."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if self.path.exists() and self.path.is_symlink():
            raise WorkerControlError("checkpoint path must not be a symlink")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS worker_checkpoints (
                    run_id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    repository_fingerprint TEXT NOT NULL,
                    authority_digest TEXT NOT NULL,
                    status TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    steps_used INTEGER NOT NULL,
                    actions_used INTEGER NOT NULL,
                    cost_used TEXT NOT NULL,
                    deadline_at TEXT NOT NULL,
                    active_conflict_domains TEXT NOT NULL,
                    last_evidence_refs TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    checkpoint_digest TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _checkpoint(row: sqlite3.Row) -> WorkerCheckpoint:
        return WorkerCheckpoint(
            run_id=row["run_id"],
            objective=row["objective"],
            repository_fingerprint=row["repository_fingerprint"],
            authority_digest=row["authority_digest"],
            status=row["status"],
            revision=int(row["revision"]),
            steps_used=int(row["steps_used"]),
            actions_used=int(row["actions_used"]),
            cost_used=Decimal(row["cost_used"]),
            deadline_at=datetime.fromisoformat(row["deadline_at"]),
            active_conflict_domains=tuple(json.loads(row["active_conflict_domains"])),
            last_evidence_refs=tuple(json.loads(row["last_evidence_refs"])),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            checkpoint_digest=row["checkpoint_digest"],
        )

    def get(self, run_id: str) -> WorkerCheckpoint | None:
        rid = _id(run_id, "run_id")
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM worker_checkpoints WHERE run_id=?",
                (rid,),
            ).fetchone()
        return None if row is None else self._checkpoint(row)

    def put(
        self,
        checkpoint: WorkerCheckpoint,
        *,
        expected_revision: int | None,
    ) -> WorkerCheckpoint:
        if not isinstance(checkpoint, WorkerCheckpoint):
            raise TypeError("checkpoint must be WorkerCheckpoint")
        with sqlite3.connect(self.path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT revision FROM worker_checkpoints WHERE run_id=?",
                (checkpoint.run_id,),
            ).fetchone()
            current = None if row is None else int(row["revision"])
            if expected_revision is None:
                if current is not None:
                    raise WorkerControlError("worker checkpoint already exists")
            elif current != expected_revision:
                raise WorkerControlError(
                    f"stale checkpoint write: expected revision {expected_revision}, current {current}"
                )
            conn.execute(
                """
                INSERT INTO worker_checkpoints(
                    run_id,objective,repository_fingerprint,authority_digest,status,
                    revision,steps_used,actions_used,cost_used,deadline_at,
                    active_conflict_domains,last_evidence_refs,updated_at,checkpoint_digest
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(run_id) DO UPDATE SET
                    objective=excluded.objective,
                    repository_fingerprint=excluded.repository_fingerprint,
                    authority_digest=excluded.authority_digest,
                    status=excluded.status,
                    revision=excluded.revision,
                    steps_used=excluded.steps_used,
                    actions_used=excluded.actions_used,
                    cost_used=excluded.cost_used,
                    deadline_at=excluded.deadline_at,
                    active_conflict_domains=excluded.active_conflict_domains,
                    last_evidence_refs=excluded.last_evidence_refs,
                    updated_at=excluded.updated_at,
                    checkpoint_digest=excluded.checkpoint_digest
                """,
                (
                    checkpoint.run_id,
                    checkpoint.objective,
                    checkpoint.repository_fingerprint,
                    checkpoint.authority_digest,
                    checkpoint.status,
                    checkpoint.revision,
                    checkpoint.steps_used,
                    checkpoint.actions_used,
                    str(checkpoint.cost_used),
                    checkpoint.deadline_at.isoformat(),
                    json.dumps(list(checkpoint.active_conflict_domains), sort_keys=True),
                    json.dumps(list(checkpoint.last_evidence_refs), sort_keys=True),
                    checkpoint.updated_at.isoformat(),
                    checkpoint.checkpoint_digest,
                ),
            )
        return checkpoint


def _checkpoint(
    *,
    run_id: str,
    objective: str,
    repository_fingerprint: str,
    authority_digest: str,
    status: str,
    revision: int,
    steps_used: int,
    actions_used: int,
    cost_used: Decimal,
    deadline_at: datetime,
    active_conflict_domains: tuple[str, ...],
    evidence_refs: tuple[str, ...],
    updated_at: datetime,
) -> WorkerCheckpoint:
    material = {
        "run_id": run_id,
        "objective": objective,
        "repository_fingerprint": repository_fingerprint,
        "authority_digest": authority_digest,
        "status": status,
        "revision": revision,
        "steps_used": steps_used,
        "actions_used": actions_used,
        "cost_used": str(cost_used),
        "deadline_at": deadline_at.isoformat(),
        "active_conflict_domains": list(active_conflict_domains),
        "evidence_refs": list(evidence_refs),
        "updated_at": updated_at.isoformat(),
    }
    return WorkerCheckpoint(
        run_id=run_id,
        objective=objective,
        repository_fingerprint=repository_fingerprint,
        authority_digest=authority_digest,
        status=status,
        revision=revision,
        steps_used=steps_used,
        actions_used=actions_used,
        cost_used=cost_used,
        deadline_at=deadline_at,
        active_conflict_domains=active_conflict_domains,
        last_evidence_refs=evidence_refs,
        updated_at=updated_at,
        checkpoint_digest=_digest(material),
    )


class AutonomousWorkerController:
    def __init__(self, store: WorkerCheckpointStore, budget: WorkerBudget) -> None:
        if not isinstance(store, WorkerCheckpointStore):
            raise TypeError("store must be WorkerCheckpointStore")
        if not isinstance(budget, WorkerBudget):
            raise TypeError("budget must be WorkerBudget")
        self.store = store
        self.budget = budget

    def start(
        self,
        *,
        run_id: str,
        objective: str,
        repository_fingerprint: str,
        authority_digest: str,
        deadline_at: datetime,
        now: datetime,
        evidence_refs: Iterable[str],
    ) -> WorkerCheckpoint:
        instant = _utc(now, "now")
        deadline = _utc(deadline_at, "deadline_at")
        if deadline <= instant:
            raise WorkerControlError("worker deadline must be in the future")
        refs = tuple(sorted({_id(item, "evidence_ref", maximum=1024) for item in evidence_refs}))
        if not refs:
            raise WorkerControlError("worker start requires authority evidence")
        cp = _checkpoint(
            run_id=_id(run_id, "run_id"),
            objective=_id(objective, "objective", maximum=4096),
            repository_fingerprint=_sha(repository_fingerprint, "repository_fingerprint"),
            authority_digest=_sha(authority_digest, "authority_digest"),
            status="active",
            revision=0,
            steps_used=0,
            actions_used=0,
            cost_used=Decimal("0"),
            deadline_at=deadline,
            active_conflict_domains=(),
            evidence_refs=refs,
            updated_at=instant,
        )
        return self.store.put(cp, expected_revision=None)

    def _require_live(
        self,
        cp: WorkerCheckpoint,
        *,
        repository_fingerprint: str,
        now: datetime,
    ) -> None:
        instant = _utc(now, "now")
        if cp.status != "active":
            raise WorkerControlError(f"worker is not active: {cp.status}")
        if instant >= cp.deadline_at:
            raise WorkerControlError("worker deadline exhausted")
        if _sha(repository_fingerprint, "repository_fingerprint") != cp.repository_fingerprint:
            raise WorkerControlError("stale repository fingerprint")

    def checkpoint_step(
        self,
        run_id: str,
        *,
        repository_fingerprint: str,
        cost_delta: object,
        action_delta: int,
        conflict_domains: Iterable[str] = (),
        evidence_refs: Iterable[str],
        now: datetime,
    ) -> WorkerCheckpoint:
        cp = self.store.get(run_id)
        if cp is None:
            raise WorkerControlError("unknown worker run")
        self._require_live(cp, repository_fingerprint=repository_fingerprint, now=now)
        if isinstance(action_delta, bool) or not isinstance(action_delta, int) or action_delta < 0:
            raise ValueError("action_delta must be non-negative integer")
        next_steps = cp.steps_used + 1
        next_actions = cp.actions_used + action_delta
        next_cost = cp.cost_used + _money(cost_delta, "cost_delta")
        if next_steps > self.budget.max_steps:
            raise WorkerControlError("worker step budget exhausted")
        if next_actions > self.budget.max_actions:
            raise WorkerControlError("worker action budget exhausted")
        if next_cost > self.budget.max_cost:
            raise WorkerControlError("worker cost budget exhausted")
        domains = tuple(sorted({_id(item, "conflict_domain") for item in conflict_domains}))
        if len(domains) != len(set(domains)):
            raise WorkerControlError("duplicate conflict domain")
        refs = tuple(sorted({_id(item, "evidence_ref", maximum=1024) for item in evidence_refs}))
        if not refs:
            raise WorkerControlError("worker checkpoint requires evidence")
        instant = _utc(now, "now")
        updated = _checkpoint(
            run_id=cp.run_id,
            objective=cp.objective,
            repository_fingerprint=cp.repository_fingerprint,
            authority_digest=cp.authority_digest,
            status="active",
            revision=cp.revision + 1,
            steps_used=next_steps,
            actions_used=next_actions,
            cost_used=next_cost,
            deadline_at=cp.deadline_at,
            active_conflict_domains=domains,
            evidence_refs=refs,
            updated_at=instant,
        )
        return self.store.put(updated, expected_revision=cp.revision)

    def interrupt(
        self,
        run_id: str,
        *,
        evidence_ref: str,
        now: datetime,
    ) -> WorkerCheckpoint:
        cp = self.store.get(run_id)
        if cp is None:
            raise WorkerControlError("unknown worker run")
        if cp.status != "active":
            raise WorkerControlError("only active worker can be interrupted")
        instant = _utc(now, "now")
        updated = _checkpoint(
            run_id=cp.run_id,
            objective=cp.objective,
            repository_fingerprint=cp.repository_fingerprint,
            authority_digest=cp.authority_digest,
            status="interrupted",
            revision=cp.revision + 1,
            steps_used=cp.steps_used,
            actions_used=cp.actions_used,
            cost_used=cp.cost_used,
            deadline_at=cp.deadline_at,
            active_conflict_domains=cp.active_conflict_domains,
            evidence_refs=(_id(evidence_ref, "evidence_ref"),),
            updated_at=instant,
        )
        return self.store.put(updated, expected_revision=cp.revision)

    def resume(
        self,
        run_id: str,
        *,
        repository_fingerprint: str,
        resume_authority_ref: str,
        now: datetime,
    ) -> WorkerCheckpoint:
        cp = self.store.get(run_id)
        if cp is None:
            raise WorkerControlError("unknown worker run")
        instant = _utc(now, "now")
        if cp.status != "interrupted":
            raise WorkerControlError("only interrupted worker can resume")
        if instant >= cp.deadline_at:
            raise WorkerControlError("worker deadline exhausted")
        fingerprint = _sha(repository_fingerprint, "repository_fingerprint")
        if fingerprint != cp.repository_fingerprint:
            raise WorkerControlError("stale repository fingerprint")
        updated = _checkpoint(
            run_id=cp.run_id,
            objective=cp.objective,
            repository_fingerprint=cp.repository_fingerprint,
            authority_digest=cp.authority_digest,
            status="active",
            revision=cp.revision + 1,
            steps_used=cp.steps_used,
            actions_used=cp.actions_used,
            cost_used=cp.cost_used,
            deadline_at=cp.deadline_at,
            active_conflict_domains=(),
            evidence_refs=(_id(resume_authority_ref, "resume_authority_ref"),),
            updated_at=instant,
        )
        return self.store.put(updated, expected_revision=cp.revision)

    def human_override(
        self,
        run_id: str,
        *,
        override_ref: str,
        now: datetime,
    ) -> WorkerCheckpoint:
        cp = self.store.get(run_id)
        if cp is None:
            raise WorkerControlError("unknown worker run")
        if cp.status in {"completed", "halted"}:
            return cp
        instant = _utc(now, "now")
        updated = _checkpoint(
            run_id=cp.run_id,
            objective=cp.objective,
            repository_fingerprint=cp.repository_fingerprint,
            authority_digest=cp.authority_digest,
            status="halted",
            revision=cp.revision + 1,
            steps_used=cp.steps_used,
            actions_used=cp.actions_used,
            cost_used=cp.cost_used,
            deadline_at=cp.deadline_at,
            active_conflict_domains=(),
            evidence_refs=(_id(override_ref, "override_ref"),),
            updated_at=instant,
        )
        return self.store.put(updated, expected_revision=cp.revision)

    def complete(
        self,
        run_id: str,
        *,
        repository_fingerprint: str,
        evidence_refs: Iterable[str],
        now: datetime,
    ) -> WorkerCheckpoint:
        cp = self.store.get(run_id)
        if cp is None:
            raise WorkerControlError("unknown worker run")
        self._require_live(cp, repository_fingerprint=repository_fingerprint, now=now)
        refs = tuple(sorted({_id(item, "evidence_ref", maximum=1024) for item in evidence_refs}))
        if not refs:
            raise WorkerControlError("completion requires evidence")
        instant = _utc(now, "now")
        updated = _checkpoint(
            run_id=cp.run_id,
            objective=cp.objective,
            repository_fingerprint=cp.repository_fingerprint,
            authority_digest=cp.authority_digest,
            status="completed",
            revision=cp.revision + 1,
            steps_used=cp.steps_used,
            actions_used=cp.actions_used,
            cost_used=cp.cost_used,
            deadline_at=cp.deadline_at,
            active_conflict_domains=(),
            evidence_refs=refs,
            updated_at=instant,
        )
        return self.store.put(updated, expected_revision=cp.revision)


__all__ = [
    "AutonomousWorkerController",
    "WorkerBudget",
    "WorkerCheckpoint",
    "WorkerCheckpointStore",
    "WorkerControlError",
]
