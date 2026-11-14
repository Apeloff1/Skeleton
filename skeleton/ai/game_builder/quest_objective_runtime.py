"""Quest/objective runtime (#807 B028).

Objectives, dependencies, rewards and failure states that are machine-verifiable
and persistable. Pure, deterministic, stdlib-only; no I/O. B021 (canonical
mechanics core) is not on main yet, so state transitions are expressed as a
typed, sealed event log that a future mechanics core can drive.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

SCHEMA_ID = "gameplay.quest_runtime.v1"


class QuestError(ValueError):
    """Invalid quest definition, transition or persisted state (fail closed)."""


class ObjectiveState(str, Enum):
    LOCKED = "locked"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


_TERMINAL = {ObjectiveState.COMPLETED, ObjectiveState.FAILED}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Reward:
    kind: str
    amount: int = 1

    def to_mapping(self) -> dict[str, Any]:
        return {"kind": self.kind, "amount": self.amount}


@dataclass(frozen=True, slots=True)
class Objective:
    objective_id: str
    requires: tuple[str, ...] = ()
    target: int = 1
    rewards: tuple[Reward, ...] = ()
    fail_on: tuple[str, ...] = ()  # event tags that fail this objective
    optional: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Objective":
        allowed = {"id", "requires", "target", "rewards", "fail_on", "optional"}
        unknown = set(data) - allowed
        if unknown:
            raise QuestError(f"unknown objective keys: {sorted(unknown)}")
        oid = data.get("id")
        if not isinstance(oid, str) or not oid:
            raise QuestError("objective id required")
        target = data.get("target", 1)
        if isinstance(target, bool) or not isinstance(target, int) or target < 1:
            raise QuestError(f"{oid}: target must be a positive int")
        rewards = []
        for r in data.get("rewards", ()):
            amount = r.get("amount", 1)
            if not isinstance(r.get("kind"), str) or isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
                raise QuestError(f"{oid}: invalid reward")
            rewards.append(Reward(r["kind"], amount))
        return cls(oid, tuple(data.get("requires", ())), target, tuple(rewards),
                   tuple(data.get("fail_on", ())), bool(data.get("optional", False)))

    def to_mapping(self) -> dict[str, Any]:
        return {"id": self.objective_id, "requires": list(self.requires), "target": self.target,
                "rewards": [r.to_mapping() for r in self.rewards], "fail_on": list(self.fail_on),
                "optional": self.optional}


@dataclass(frozen=True, slots=True)
class QuestDefinition:
    quest_id: str
    objectives: tuple[Objective, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "QuestDefinition":
        qid = data.get("id")
        if not isinstance(qid, str) or not qid:
            raise QuestError("quest id required")
        objectives = tuple(Objective.from_mapping(o) for o in data.get("objectives", ()))
        definition = cls(qid, objectives)
        definition.validate()
        return definition

    def to_mapping(self) -> dict[str, Any]:
        return {"id": self.quest_id, "objectives": [o.to_mapping() for o in self.objectives]}

    @property
    def digest(self) -> str:
        return _digest(self.to_mapping())

    def by_id(self) -> dict[str, Objective]:
        return {o.objective_id: o for o in self.objectives}

    def validate(self) -> None:
        """Unique ids, known deps, acyclic graph, at least one required objective."""
        ids = [o.objective_id for o in self.objectives]
        if not ids:
            raise QuestError("quest must have objectives")
        if len(set(ids)) != len(ids):
            raise QuestError("duplicate objective ids")
        known = set(ids)
        for o in self.objectives:
            missing = set(o.requires) - known
            if missing:
                raise QuestError(f"{o.objective_id}: unknown dependencies {sorted(missing)}")
        self.topological_order()
        if all(o.optional for o in self.objectives):
            raise QuestError("quest needs at least one required objective")

    def topological_order(self) -> tuple[str, ...]:
        objs = self.by_id()
        order: list[str] = []
        state: dict[str, int] = {}

        def visit(oid: str) -> None:
            if state.get(oid) == 2:
                return
            if state.get(oid) == 1:
                raise QuestError(f"dependency cycle at {oid}")
            state[oid] = 1
            for dep in sorted(objs[oid].requires):
                visit(dep)
            state[oid] = 2
            order.append(oid)

        for oid in sorted(objs):
            visit(oid)
        return tuple(order)


@dataclass(slots=True)
class QuestRuntime:
    definition: QuestDefinition
    progress: dict[str, int] = field(default_factory=dict)
    states: dict[str, ObjectiveState] = field(default_factory=dict)
    log: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        for o in self.definition.objectives:
            self.progress.setdefault(o.objective_id, 0)
            self.states.setdefault(o.objective_id, ObjectiveState.LOCKED)
        self._unlock()

    def _unlock(self) -> None:
        for oid in self.definition.topological_order():
            obj = self.definition.by_id()[oid]
            if self.states[oid] is ObjectiveState.LOCKED and all(
                self.states[d] is ObjectiveState.COMPLETED for d in obj.requires
            ):
                self.states[oid] = ObjectiveState.ACTIVE

    def advance(self, objective_id: str, amount: int = 1) -> ObjectiveState:
        if objective_id not in self.states:
            raise QuestError(f"unknown objective {objective_id}")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
            raise QuestError("amount must be a positive int")
        state = self.states[objective_id]
        if state is not ObjectiveState.ACTIVE:
            raise QuestError(f"{objective_id} is {state.value}, not active")
        obj = self.definition.by_id()[objective_id]
        self.progress[objective_id] = min(obj.target, self.progress[objective_id] + amount)
        self.log.append({"op": "advance", "objective": objective_id, "amount": amount})
        if self.progress[objective_id] >= obj.target:
            self.states[objective_id] = ObjectiveState.COMPLETED
            self._unlock()
        return self.states[objective_id]

    def signal(self, tag: str) -> list[str]:
        """Apply a world event tag; active/locked objectives listing it fail."""
        failed = []
        for o in self.definition.objectives:
            if tag in o.fail_on and self.states[o.objective_id] not in _TERMINAL:
                self.states[o.objective_id] = ObjectiveState.FAILED
                failed.append(o.objective_id)
        self.log.append({"op": "signal", "tag": tag})
        # Dependents of a failed objective can never unlock: fail them too.
        changed = True
        while changed:
            changed = False
            for o in self.definition.objectives:
                if self.states[o.objective_id] is ObjectiveState.LOCKED and any(
                    self.states[d] is ObjectiveState.FAILED for d in o.requires
                ):
                    self.states[o.objective_id] = ObjectiveState.FAILED
                    failed.append(o.objective_id)
                    changed = True
        return failed

    @property
    def status(self) -> str:
        required = [o for o in self.definition.objectives if not o.optional]
        if any(self.states[o.objective_id] is ObjectiveState.FAILED for o in required):
            return "failed"
        if all(self.states[o.objective_id] is ObjectiveState.COMPLETED for o in required):
            return "completed"
        return "in_progress"

    def earned_rewards(self) -> list[dict[str, Any]]:
        return [r.to_mapping() for o in self.definition.objectives
                if self.states[o.objective_id] is ObjectiveState.COMPLETED for r in o.rewards]

    def snapshot(self) -> dict[str, Any]:
        body = {
            "schema": SCHEMA_ID,
            "definition_digest": self.definition.digest,
            "progress": dict(sorted(self.progress.items())),
            "states": {k: v.value for k, v in sorted(self.states.items())},
            "log": list(self.log),
        }
        return {**body, "digest": _digest(body)}

    @classmethod
    def restore(cls, definition: QuestDefinition, snapshot: Mapping[str, Any]) -> "QuestRuntime":
        """Restore by replaying the log; any tamper or mismatch fails closed."""
        if snapshot.get("schema") != SCHEMA_ID:
            raise QuestError("unsupported quest snapshot schema")
        body = {k: v for k, v in snapshot.items() if k != "digest"}
        if snapshot.get("digest") != _digest(body):
            raise QuestError("quest snapshot digest mismatch")
        if snapshot.get("definition_digest") != definition.digest:
            raise QuestError("quest snapshot belongs to a different definition")
        runtime = cls(definition)
        for entry in snapshot.get("log", ()):
            if entry.get("op") == "advance":
                runtime.advance(entry["objective"], entry["amount"])
            elif entry.get("op") == "signal":
                runtime.signal(entry["tag"])
            else:
                raise QuestError("unknown log op")
        if runtime.snapshot() != dict(snapshot):
            raise QuestError("replayed quest state diverges from snapshot")
        return runtime


def run_quest(definition: Mapping[str, Any] | QuestDefinition, events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Deterministically apply events ({'advance': id, 'amount': n} | {'signal': tag})."""
    qdef = definition if isinstance(definition, QuestDefinition) else QuestDefinition.from_mapping(definition)
    runtime = QuestRuntime(qdef)
    for event in events:
        if "advance" in event:
            runtime.advance(event["advance"], event.get("amount", 1))
        elif "signal" in event:
            runtime.signal(event["signal"])
        else:
            raise QuestError("unknown event")
    return {"status": runtime.status, "rewards": runtime.earned_rewards(), "snapshot": runtime.snapshot()}


__all__ = ["SCHEMA_ID", "Objective", "ObjectiveState", "QuestDefinition", "QuestError",
           "QuestRuntime", "Reward", "run_quest"]
