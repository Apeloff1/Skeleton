"""Swarm DAG — attested task graph (sync port of gf-gameforge swarm.rs).

Work enters as nodes with declared dependencies; the DAG emits execution
waves in topological order via ``ready_wave()``. Cycles are rejected at
submission.

Byzantine note (ported from gameforge-rs): a node is only ``Done`` when its
executor reports completion *and* the result was attested — unwitnessed
completion means nothing. ``complete()`` therefore requires a non-None
attested result payload; there is no ``complete_unattested`` API that can
mark Done.

Source: Apeloff1/gameforge-rs crates/gf-gameforge/src/swarm.rs
Pure sync (no asyncio) to match Skeleton scheduler style.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class TaskNode:
    id: str
    capability: str
    payload: Any
    deps: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    executor: Optional[str] = None
    result: Optional[Any] = None


class SubmitError(Exception):
    """Rejected submit: unknown dependency, cycle, or duplicate id."""

    def __init__(self, kind: str, detail: str) -> None:
        self.kind = kind  # "unknown_dependency" | "cycle" | "duplicate"
        self.detail = detail
        super().__init__(f"{kind}: {detail}")

    @classmethod
    def unknown_dependency(cls, dep: str) -> "SubmitError":
        return cls("unknown_dependency", dep)

    @classmethod
    def cycle(cls, task_id: str) -> "SubmitError":
        return cls("cycle", task_id)

    @classmethod
    def duplicate(cls, task_id: str) -> "SubmitError":
        return cls("duplicate", task_id)


class SwarmDag:
    """Synchronous dependency DAG with attested completion.

    Done is reached only via ``complete(task_id, result)`` with a non-None
    attested result. Failed tasks do not unlock dependents.
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, TaskNode] = {}

    def submit(
        self,
        id: str,
        capability: str,
        payload: Any,
        deps: Optional[List[str]] = None,
    ) -> None:
        """Submit a task. Dependencies must exist; graph must stay acyclic."""
        deps = list(deps or [])
        if id in self._nodes:
            raise SubmitError.duplicate(id)
        # Self-edge is a cycle even though the id is not yet in the map
        # (would otherwise look like an unknown dependency).
        if id in deps or self._would_cycle(id, deps):
            raise SubmitError.cycle(id)
        for d in deps:
            if d not in self._nodes:
                raise SubmitError.unknown_dependency(d)
        self._nodes[id] = TaskNode(
            id=id,
            capability=capability,
            payload=payload,
            deps=deps,
            status=TaskStatus.PENDING,
        )

    def _would_cycle(self, new_id: str, deps: List[str]) -> bool:
        """True if adding edges deps -> new_id would create a cycle.

        With only fresh ids this reduces to self-reference (handled by
        caller), but we also walk: if new_id were already reachable from
        a dep via reverse edges (dependents), adding would cycle. Since
        new_id is absent, check whether any dep can reach another dep
        that... actually for a fresh id the only cycle is self-ref.
        Still: walk from each dep following *outgoing* dependency edges
        (task -> its deps? No — edge direction for topo is dep completes
        before task, so dep -> task). From existing nodes, can we reach
        new_id? No, new_id not present. Self-ref is the sole case for
        fresh submit — keep the DFS for clarity if deps somehow list a
        path that includes new_id (already covered) or if we later allow
        richer graphs.
        """
        # Reachability: starting from deps, follow edges to *dependents*
        # that already exist? For fresh id impossible. Detect if walking
        # *up* the dep chain from deps ever sees new_id (self via alias).
        seen: Set[str] = set()
        stack = list(deps)
        while stack:
            cur = stack.pop()
            if cur == new_id:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            node = self._nodes.get(cur)
            if node is None:
                continue
            stack.extend(node.deps)
        return False

    def ready_wave(self) -> List[TaskNode]:
        """Mark Pending tasks whose deps are all Done as Ready; return wave.

        Waves are the only honest way through the labyrinth — nobody skips
        a gate. A task only unlocks dependents after attested ``complete``.
        """
        done: Set[str] = {
            n.id for n in self._nodes.values() if n.status == TaskStatus.DONE
        }
        wave: List[TaskNode] = []
        for n in self._nodes.values():
            if n.status == TaskStatus.PENDING and all(d in done for d in n.deps):
                n.status = TaskStatus.READY
                wave.append(n)
        return list(wave)

    def claim(self, task_id: str, executor: str) -> Optional[TaskNode]:
        """Claim a Ready task for an executor. Ready → Running."""
        n = self._nodes.get(task_id)
        if n is None or n.status != TaskStatus.READY:
            return None
        n.status = TaskStatus.RUNNING
        n.executor = executor
        return n

    def complete(self, task_id: str, result: Any) -> bool:
        """Attested completion. Running → Done only with non-None result.

        Unwitnessed / unattested completion is rejected (returns False and
        leaves status unchanged). There is no complete_unattested path to Done.
        """
        if result is None:
            return False
        n = self._nodes.get(task_id)
        if n is None or n.status != TaskStatus.RUNNING:
            return False
        n.status = TaskStatus.DONE
        n.result = result
        return True

    def fail(self, task_id: str) -> bool:
        """Running → Failed. Does not unlock dependents."""
        n = self._nodes.get(task_id)
        if n is None or n.status != TaskStatus.RUNNING:
            return False
        n.status = TaskStatus.FAILED
        return True

    def get(self, task_id: str) -> Optional[TaskNode]:
        return self._nodes.get(task_id)

    def stats(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for n in self._nodes.values():
            label = n.status.value
            counts[label] = counts.get(label, 0) + 1
        return {"tasks": len(self._nodes), "by_status": counts}
