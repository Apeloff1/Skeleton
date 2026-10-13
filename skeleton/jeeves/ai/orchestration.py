"""Deterministic, non-executing Jeeves orchestration records.

Supervisor plans may delegate to Secretary plans; Secretary plans may delegate to
Workers. Reverse delegation is rejected.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping, Sequence

from ._canonical import bounded_text, canonical_digest, frozen_mapping
from .contracts import Authority, MAX_EVIDENCE

MAX_TASKS = 512
MAX_DEPENDENCIES = 64
MAX_METADATA_BYTES = 32 * 1024


class OrchestrState(str, Enum):
    NEW = "new"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"


_ALLOWED_DELEGATION = {
    Authority.SUPERVISOR: frozenset({Authority.SUPERVISOR, Authority.SECRETARY, Authority.WORKER}),
    Authority.SECRETARY: frozenset({Authority.SECRETARY, Authority.WORKER}),
    Authority.WORKER: frozenset({Authority.WORKER}),
}


def _digest(value: Any) -> str:
    return canonical_digest(value, max_bytes=MAX_METADATA_BYTES)


@dataclass(frozen=True)
class OrchestrRecord:
    name: str
    state: OrchestrState = OrchestrState.NEW
    payload: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()
    authority: Authority = Authority.WORKER
    parent: str | None = None
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        bounded_text(self.name, "task name")
        if not isinstance(self.state, OrchestrState):
            raise ValueError("invalid orchestration state")
        if not isinstance(self.authority, Authority):
            raise ValueError("invalid authority")
        if self.parent is not None:
            bounded_text(self.parent, "parent")
            if self.parent == self.name:
                raise ValueError("task cannot parent itself")
        if not isinstance(self.dependencies, tuple) or len(self.dependencies) > MAX_DEPENDENCIES:
            raise ValueError("invalid dependencies")
        deps = tuple(bounded_text(dep, "dependency") for dep in self.dependencies)
        if self.name in deps or len(set(deps)) != len(deps):
            raise ValueError("invalid dependency set")
        if not isinstance(self.evidence, tuple) or len(self.evidence) > MAX_EVIDENCE:
            raise ValueError("invalid evidence")
        evidence = tuple(bounded_text(item, "evidence") for item in self.evidence)
        object.__setattr__(self, "payload", frozen_mapping(self.payload, max_bytes=MAX_METADATA_BYTES))
        object.__setattr__(self, "dependencies", deps)
        object.__setattr__(self, "evidence", evidence)

    @property
    def digest(self) -> str:
        return _digest({
            "authority": self.authority.value,
            "dependencies": self.dependencies,
            "evidence": self.evidence,
            "name": self.name,
            "parent": self.parent,
            "payload": dict(self.payload),
            "state": self.state.value,
            "v": 1,
        })


@dataclass(frozen=True)
class OrchestrLedger:
    records: tuple[OrchestrRecord, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple):
            raise ValueError("records must be a tuple")
        _validate_graph(self.records)

    def append(self, record: OrchestrRecord) -> "OrchestrLedger":
        if not isinstance(record, OrchestrRecord):
            raise ValueError("invalid record")
        return OrchestrLedger(self.records + (record,))

    def ready_names(self) -> tuple[str, ...]:
        """Deterministic dependency frontier; blocked and failed work stays withheld.

        A child may only enter the frontier when its parent has explicitly
        become ready/running. The frontier is information, not a dispatch queue.
        """
        by_name = {record.name: record for record in self.records}
        ready: list[str] = []
        for record in self.records:
            if record.state not in (OrchestrState.NEW, OrchestrState.READY):
                continue
            if not all(by_name[dep].state is OrchestrState.DONE
                       for dep in record.dependencies):
                continue
            if record.parent is not None and by_name[record.parent].state not in (
                OrchestrState.READY, OrchestrState.RUNNING,
            ):
                continue
            ready.append(record.name)
        return tuple(sorted(ready))

    def transition(self, name: str, state: OrchestrState, *,
                   evidence: tuple[str, ...] = ()) -> "OrchestrLedger":
        """Return an authority-preserving, evidence-bearing state update.

        This transition never executes the task, mints a tool grant, or
        substitutes orchestration completion for external execution proof.
        """
        bounded_text(name, "task name")
        if not isinstance(state, OrchestrState):
            raise ValueError("invalid target orchestration state")
        if not isinstance(evidence, tuple):
            raise ValueError("transition evidence must be a tuple")
        transitions = {
            OrchestrState.NEW: frozenset({OrchestrState.READY, OrchestrState.BLOCKED}),
            OrchestrState.READY: frozenset({
                OrchestrState.RUNNING, OrchestrState.BLOCKED, OrchestrState.FAILED,
            }),
            OrchestrState.RUNNING: frozenset({
                OrchestrState.DONE, OrchestrState.BLOCKED, OrchestrState.FAILED,
            }),
            OrchestrState.BLOCKED: frozenset({
                OrchestrState.READY, OrchestrState.FAILED,
            }),
            OrchestrState.FAILED: frozenset({OrchestrState.READY}),
            OrchestrState.DONE: frozenset(),
        }
        by_name = {record.name: record for record in self.records}
        current = by_name.get(name)
        if current is None:
            raise ValueError("unknown orchestration task")
        if state not in transitions[current.state]:
            raise ValueError("invalid orchestration state transition")
        if state in (OrchestrState.READY, OrchestrState.RUNNING, OrchestrState.DONE):
            if any(by_name[dep].state is not OrchestrState.DONE
                   for dep in current.dependencies):
                raise ValueError("orchestration dependencies have not completed")
            if current.parent is not None and by_name[current.parent].state not in (
                OrchestrState.READY, OrchestrState.RUNNING,
            ):
                raise ValueError("parent is not accepting delegated work")
        if state is OrchestrState.DONE:
            if any(child.parent == name and child.state is not OrchestrState.DONE
                   for child in self.records):
                raise ValueError("cannot close task with unfinished children")
            if not current.evidence and not evidence:
                raise ValueError("completed orchestration requires evidence")
        updated = replace(current, state=state, evidence=current.evidence + evidence)
        return OrchestrLedger(tuple(
            updated if record.name == name else record for record in self.records
        ))

    @property
    def digest(self) -> str:
        # A full 512-task ledger exceeds the per-task 32 KiB payload budget.
        # Bound the aggregate independently while retaining per-record bounds.
        return canonical_digest(
            {"records": [record.digest for record in self.records], "v": 1},
            max_bytes=128 * 1024,
        )


def _validate_graph(records: Sequence[OrchestrRecord]) -> None:
    if isinstance(records, (str, bytes)):
        raise ValueError("records must be orchestration records")
    if len(records) > MAX_TASKS:
        raise ValueError("too many tasks")
    by_name: dict[str, OrchestrRecord] = {}
    for record in records:
        if not isinstance(record, OrchestrRecord):
            raise ValueError("invalid record")
        if record.name in by_name:
            raise ValueError("duplicate record")
        by_name[record.name] = record

    for record in records:
        if record.parent is not None:
            parent = by_name.get(record.parent)
            if parent is None:
                raise ValueError("missing parent")
            if record.authority not in _ALLOWED_DELEGATION[parent.authority]:
                raise ValueError("authority escalation")
        for dep in record.dependencies:
            dependency = by_name.get(dep)
            if dependency is None:
                raise ValueError("missing dependency")
            if dependency.authority not in _ALLOWED_DELEGATION[record.authority]:
                raise ValueError("dependency authority escalation")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise ValueError("orchestration cycle")
        visiting.add(name)
        record = by_name[name]
        edges = list(record.dependencies)
        if record.parent is not None:
            edges.append(record.parent)
        for edge in edges:
            visit(edge)
        visiting.remove(name)
        visited.add(name)

    for name in by_name:
        visit(name)


def validate_orchestr(records: Sequence[OrchestrRecord]) -> tuple[str, ...]:
    if isinstance(records, (str, bytes)):
        raise ValueError("records must be a sequence")
    materialized = tuple(records)
    _validate_graph(materialized)
    return tuple(record.digest for record in materialized)
