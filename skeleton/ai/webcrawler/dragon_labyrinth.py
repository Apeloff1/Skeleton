"""Dragon labyrinth: deterministic, auditable experiment graph.

Models complex gameplay-learning and game-building as a DAG of immutable
work specifications. Workers lease ready nodes; retries, budgets, approval
gates, provenance and terminal failures are explicit. This is a control
plane, not a claim that vision models or game engines have executed.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import sqlite3


class WorkKind(str, Enum):
    CAPTURE_REVIEW = "capture_review"
    FRAME_EXTRACTION = "frame_extraction"
    TEMPORAL_ANALYSIS = "temporal_analysis"
    MECHANIC_HYPOTHESIS = "mechanic_hypothesis"
    CAUSAL_CHALLENGE = "causal_challenge"
    TASTE_CONFIRMATION = "taste_confirmation"
    KNOWLEDGE_DISTILLATION = "knowledge_distillation"
    ORIGINALITY_REVIEW = "originality_review"
    DESIGN_PROPOSAL = "design_proposal"
    ADVERSARIAL_CRITIQUE = "adversarial_critique"
    PROTOTYPE_BUILD = "prototype_build"
    PLAYTEST = "playtest"
    REGRESSION_GATE = "regression_gate"
    RELEASE_REVIEW = "release_review"


class WorkStatus(str, Enum):
    PENDING = "pending"
    LEASED = "leased"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class WorkSpec:
    key: str
    kind: WorkKind
    dependencies: tuple[str, ...] = ()
    approval_required: bool = False
    max_attempts: int = 3
    cost_units: int = 1


@dataclass(frozen=True)
class WorkRecord:
    key: str
    kind: WorkKind
    status: WorkStatus
    attempts: int
    approval_required: bool
    cost_units: int
    lease_token: str = ""
    output_digest: str = ""


@dataclass(frozen=True)
class LabyrinthPlan:
    owner: str
    plan_id: str
    nodes: tuple[WorkSpec, ...]
    total_cost: int
    fingerprint: str


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True).encode()).hexdigest()


def plan_labyrinth(owner: str, nodes: tuple[WorkSpec, ...], *,
                   authorized: bool, max_nodes: int = 10000,
                   max_cost: int = 100000) -> LabyrinthPlan:
    if not authorized:
        raise PermissionError("planning requires authorization")
    if not isinstance(owner, str) or not 1 <= len(owner) <= 128:
        raise ValueError("invalid owner")
    if not 1 <= len(nodes) <= max_nodes:
        raise ValueError("invalid graph size")
    by_key = {}
    for node in nodes:
        if not isinstance(node.key, str) or not 1 <= len(node.key) <= 100:
            raise ValueError("invalid node key")
        if not isinstance(node.kind, WorkKind):
            raise ValueError("invalid work kind")
        if node.key in by_key:
            raise ValueError("duplicate work key")
        if not 1 <= node.max_attempts <= 20 or not 1 <= node.cost_units <= max_cost:
            raise ValueError("invalid work budget")
        if len(node.dependencies) > max_nodes or len(set(node.dependencies)) != len(node.dependencies):
            raise ValueError("invalid dependencies")
        by_key[node.key] = node
    total_cost = sum(node.cost_units * node.max_attempts for node in nodes)
    if total_cost > max_cost:
        raise ValueError("graph cost budget exceeded")
    visited, visiting = set(), set()
    def visit(key: str) -> None:
        if key in visiting:
            raise ValueError("cyclic dependency graph")
        if key in visited:
            return
        if key not in by_key:
            raise ValueError("missing dependency")
        visiting.add(key)
        for dep in by_key[key].dependencies:
            visit(dep)
        visiting.remove(key)
        visited.add(key)
    for key in sorted(by_key):
        visit(key)
    normalized = tuple(sorted(nodes, key=lambda node: node.key))
    fingerprint = _digest([
        owner, [(n.key, n.kind.value, sorted(n.dependencies),
                 n.approval_required, n.max_attempts, n.cost_units)
                for n in normalized],
    ])
    return LabyrinthPlan(owner, fingerprint[:24], normalized,
                         total_cost, fingerprint)


class DragonLabyrinth:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        db.execute("""
            CREATE TABLE IF NOT EXISTS dragon_labyrinth_plans(
                owner TEXT NOT NULL, plan_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL, PRIMARY KEY(owner,plan_id))
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS dragon_labyrinth_nodes(
                owner TEXT NOT NULL,plan_id TEXT NOT NULL,key TEXT NOT NULL,
                kind TEXT NOT NULL,status TEXT NOT NULL,
                dependencies_json TEXT NOT NULL,approval_required INTEGER NOT NULL,
                max_attempts INTEGER NOT NULL,attempts INTEGER NOT NULL,
                cost_units INTEGER NOT NULL,lease_token TEXT NOT NULL,
                output_digest TEXT NOT NULL,
                PRIMARY KEY(owner,plan_id,key))
        """)
        db.commit()

    def install(self, plan: LabyrinthPlan, *, authorized: bool) -> None:
        if not authorized:
            raise PermissionError("install requires authorization")
        checked = plan_labyrinth(plan.owner, plan.nodes, authorized=True,
                                 max_nodes=max(10000, len(plan.nodes)),
                                 max_cost=max(100000, plan.total_cost))
        if checked.fingerprint != plan.fingerprint or checked.plan_id != plan.plan_id:
            raise ValueError("plan fingerprint mismatch")
        with self.db:
            row = self.db.execute("""
                SELECT fingerprint FROM dragon_labyrinth_plans
                WHERE owner=? AND plan_id=?
            """, (plan.owner, plan.plan_id)).fetchone()
            if row:
                if row[0] != plan.fingerprint:
                    raise ValueError("plan identity conflict")
                return
            self.db.execute(
                "INSERT INTO dragon_labyrinth_plans VALUES(?,?,?)",
                (plan.owner, plan.plan_id, plan.fingerprint),
            )
            for node in plan.nodes:
                self.db.execute("""
                    INSERT INTO dragon_labyrinth_nodes VALUES(
                        ?,?,?,?,'pending',?,?,?,0,?,'','')
                """, (plan.owner, plan.plan_id, node.key, node.kind.value,
                      json.dumps(node.dependencies), int(node.approval_required),
                      node.max_attempts, node.cost_units))

    def _rows(self, owner: str, plan_id: str):
        return self.db.execute("""
            SELECT key,kind,status,dependencies_json,approval_required,
                   max_attempts,attempts,cost_units,lease_token,output_digest
            FROM dragon_labyrinth_nodes
            WHERE owner=? AND plan_id=? ORDER BY key
        """, (owner, plan_id)).fetchall()

    def status(self, owner: str, plan_id: str, *,
               authorized: bool) -> tuple[WorkRecord, ...]:
        if not authorized:
            raise PermissionError("status requires authorization")
        return tuple(WorkRecord(
            row[0], WorkKind(row[1]), WorkStatus(row[2]), row[6],
            bool(row[4]), row[7], row[8], row[9],
        ) for row in self._rows(owner, plan_id))

    def ready(self, owner: str, plan_id: str, *, authorized: bool,
              limit: int = 100) -> tuple[WorkRecord, ...]:
        if not authorized:
            raise PermissionError("ready requires authorization")
        if not 1 <= limit <= 1000:
            raise ValueError("invalid ready limit")
        rows = self._rows(owner, plan_id)
        complete = {r[0] for r in rows if r[2] == WorkStatus.COMPLETED.value}
        available = []
        for row in rows:
            if row[2] != WorkStatus.PENDING.value:
                continue
            if set(json.loads(row[3])).issubset(complete):
                available.append(WorkRecord(
                    row[0], WorkKind(row[1]), WorkStatus.PENDING,
                    row[6], bool(row[4]), row[7],
                ))
        return tuple(available[:limit])

    def lease(self, owner: str, plan_id: str, key: str, *,
              worker: str, authorized: bool,
              approval: bool = False) -> str:
        if not authorized:
            raise PermissionError("lease requires authorization")
        if not isinstance(worker, str) or not 1 <= len(worker) <= 100:
            raise ValueError("invalid worker")
        with self.db:
            ready = {item.key for item in self.ready(
                owner, plan_id, authorized=True, limit=1000,
            )}
            if key not in ready:
                raise ValueError("node not ready")
            row = self.db.execute("""
                SELECT approval_required,attempts,max_attempts
                FROM dragon_labyrinth_nodes
                WHERE owner=? AND plan_id=? AND key=?
            """, (owner, plan_id, key)).fetchone()
            if row[0] and not approval:
                raise PermissionError("human approval required")
            if row[1] >= row[2]:
                raise ValueError("attempt budget exhausted")
            token = _digest([owner, plan_id, key, worker, row[1] + 1])
            updated = self.db.execute("""
                UPDATE dragon_labyrinth_nodes SET
                    status='leased',attempts=attempts+1,lease_token=?
                WHERE owner=? AND plan_id=? AND key=? AND status='pending'
            """, (token, owner, plan_id, key)).rowcount
            if updated != 1:
                raise ValueError("lease conflict")
        return token

    def resolve(self, owner: str, plan_id: str, key: str, *,
                token: str, output_digest: str,
                success: bool, authorized: bool) -> WorkStatus:
        if not authorized:
            raise PermissionError("resolution requires authorization")
        if not isinstance(output_digest, str) or len(output_digest) != 64 or any(
            c not in "0123456789abcdef" for c in output_digest
        ):
            raise ValueError("invalid output digest")
        with self.db:
            row = self.db.execute("""
                SELECT attempts,max_attempts,lease_token,status
                FROM dragon_labyrinth_nodes
                WHERE owner=? AND plan_id=? AND key=?
            """, (owner, plan_id, key)).fetchone()
            if row is None or row[3] != "leased" or row[2] != token:
                raise PermissionError("invalid or stale lease")
            next_status = ("completed" if success else
                           "failed" if row[0] >= row[1] else "pending")
            self.db.execute("""
                UPDATE dragon_labyrinth_nodes
                SET status=?,lease_token='',output_digest=?
                WHERE owner=? AND plan_id=? AND key=?
            """, (next_status, output_digest, owner, plan_id, key))
        return WorkStatus(next_status)

    def erase(self, owner: str, *, authorized: bool) -> int:
        if not authorized:
            raise PermissionError("erasure requires authorization")
        with self.db:
            count = self.db.execute(
                "DELETE FROM dragon_labyrinth_nodes WHERE owner=?", (owner,)
            ).rowcount
            self.db.execute(
                "DELETE FROM dragon_labyrinth_plans WHERE owner=?", (owner,)
            )
        return count
