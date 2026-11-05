"""Typed, bounded DAG scheduling for host-side Jeeves task orchestration.

No model-authored plan confers tool rights. An in-flight non-idempotent node
is UNKNOWN after a crash and cannot be silently replayed. The host uses a
stable ordering, optimistic version CAS and explicit dependency checking.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping, Sequence

from .contracts import ContractHold, canonical_bytes, exact_integer, identifier, fingerprint


class PlanHold(ContractHold):
    pass


class TaskState(str, Enum):
    WAITING = "waiting"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


_TERMINAL = frozenset((
    TaskState.SUCCEEDED, TaskState.FAILED, TaskState.UNKNOWN,
    TaskState.BLOCKED, TaskState.CANCELLED,
))


@dataclass(frozen=True, slots=True)
class TaskNode:
    node_id: str
    action: str
    dependencies: tuple[str, ...] = ()
    state: TaskState = TaskState.WAITING
    attempts: int = 0
    max_attempts: int = 1
    idempotent: bool = False
    priority: int = 0
    input_sha256: str = "0" * 64
    output_sha256: str | None = None
    execution_receipt: str | None = None

    def __post_init__(self):
        identifier(self.node_id, "node")
        identifier(self.action, "action")
        if type(self.dependencies) is not tuple or len(self.dependencies) > 128:
            raise PlanHold("too many dependencies")
        if len(self.dependencies) != len(set(self.dependencies)):
            raise PlanHold("duplicate dependency")
        for dependency in self.dependencies:
            identifier(dependency, "dependency")
            if dependency == self.node_id:
                raise PlanHold("self-dependency forbidden")
        if not isinstance(self.state, TaskState):
            raise PlanHold("typed task state required")
        exact_integer(self.attempts, maximum=10000)
        exact_integer(self.max_attempts, minimum=1, maximum=10000)
        exact_integer(self.priority, minimum=0, maximum=1000000)
        if type(self.idempotent) is not bool:
            raise PlanHold("idempotence assertion must be explicit")
        if self.attempts > self.max_attempts:
            raise PlanHold("attempts exceed declared ceiling")
        for value in (self.input_sha256, self.output_sha256, self.execution_receipt):
            if value is None:
                continue
            if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise PlanHold("task digest must be lowercase sha256")
        if self.state is TaskState.SUCCEEDED and (
            self.output_sha256 is None or self.execution_receipt is None
        ):
            raise PlanHold("success requires host-checked output and receipt")
        if self.state not in _TERMINAL and self.output_sha256 is not None:
            raise PlanHold("nonterminal task cannot claim an output")

    def _changed(self, next_state: TaskState, **kwargs: Any) -> "TaskNode":
        return replace(self, state=next_state, **kwargs)


@dataclass(frozen=True, slots=True)
class TaskGraph:
    graph_id: str
    nodes: tuple[TaskNode, ...]
    version: int = 1
    scope_sha256: str = "0" * 64

    def __post_init__(self):
        identifier(self.graph_id, "graph")
        exact_integer(self.version, minimum=1)
        if type(self.nodes) is not tuple or not 1 <= len(self.nodes) <= 10000:
            raise PlanHold("bounded nonempty task graph required")
        if any(not isinstance(node, TaskNode) for node in self.nodes):
            raise PlanHold("typed task nodes required")
        index = {node.node_id: node for node in self.nodes}
        if len(index) != len(self.nodes):
            raise PlanHold("duplicate node identity")
        if any(dep not in index for node in self.nodes for dep in node.dependencies):
            raise PlanHold("dependency refers to missing node")
        if type(self.scope_sha256) is not str or len(self.scope_sha256) != 64:
            raise PlanHold("scope digest required")
        self.topological_order()

    @property
    def index(self) -> dict[str, TaskNode]:
        return {node.node_id: node for node in self.nodes}

    def topological_order(self) -> tuple[str, ...]:
        index = self.index
        ready = sorted(
            key for key, node in index.items() if not node.dependencies
        )
        emitted = []
        remaining = {k: set(v.dependencies) for k, v in index.items()}
        while ready:
            identifier_ = ready.pop(0)
            emitted.append(identifier_)
            for other_id in sorted(index):
                if identifier_ in remaining[other_id]:
                    remaining[other_id].remove(identifier_)
                    if not remaining[other_id] and other_id not in emitted and other_id not in ready:
                        ready.append(other_id)
            ready.sort()
        if len(emitted) != len(index):
            raise PlanHold("task DAG has a cycle")
        return tuple(emitted)

    @property
    def fingerprint(self) -> str:
        return fingerprint({
            "schema": "jeeves.fabric.task_graph.v1",
            "graph_id": self.graph_id,
            "version": self.version,
            "scope": self.scope_sha256,
            "nodes": [
                {
                    "id": x.node_id, "action": x.action,
                    "depends": x.dependencies, "state": x.state.value,
                    "attempts": x.attempts,
                    "max_attempts": x.max_attempts,
                    "idempotent": x.idempotent, "priority": x.priority,
                    "input": x.input_sha256, "output": x.output_sha256,
                    "receipt": x.execution_receipt,
                } for x in self.nodes
            ],
        })

    def node(self, node_id: str) -> TaskNode:
        try:
            return self.index[identifier(node_id)]
        except KeyError as exc:
            raise PlanHold("unknown task") from exc

    def ready(self, *, limit: int = 128) -> tuple[TaskNode, ...]:
        exact_integer(limit, minimum=1, maximum=10000)
        index = self.index
        candidates = []
        for node in self.nodes:
            if node.state in _TERMINAL or node.state is TaskState.IN_PROGRESS:
                continue
            dependencies = [index[d].state for d in node.dependencies]
            if any(s in (TaskState.FAILED, TaskState.UNKNOWN,
                         TaskState.BLOCKED, TaskState.CANCELLED) for s in dependencies):
                continue
            if all(s is TaskState.SUCCEEDED for s in dependencies):
                candidates.append(node)
        return tuple(sorted(candidates,
                            key=lambda n: (-n.priority, n.node_id))[:limit])

    def _update(self, node_id: str, expected_version: int, changed: TaskNode) -> "TaskGraph":
        if self.version != exact_integer(expected_version, minimum=1):
            raise PlanHold("stale graph revision")
        if changed.node_id != node_id:
            raise PlanHold("task identity cannot be changed")
        nodes = tuple(changed if n.node_id == node_id else n for n in self.nodes)
        if nodes == self.nodes:
            raise PlanHold("no-op graph transition refused")
        return TaskGraph(self.graph_id, nodes, self.version + 1, self.scope_sha256)

    def begin(self, node_id: str, *, expected_version: int) -> "TaskGraph":
        current = self.node(node_id)
        if current not in self.ready(limit=len(self.nodes)):
            raise PlanHold("task is not dependency-ready")
        if current.attempts >= current.max_attempts:
            raise PlanHold("attempt budget exhausted")
        return self._update(
            node_id, expected_version,
            current._changed(TaskState.IN_PROGRESS, attempts=current.attempts + 1),
        )

    def complete(
        self, node_id: str, *, expected_version: int,
        output_sha256: str, receipt_sha256: str,
    ) -> "TaskGraph":
        current = self.node(node_id)
        if current.state is not TaskState.IN_PROGRESS:
            raise PlanHold("task was not started")
        return self._update(node_id, expected_version, current._changed(
            TaskState.SUCCEEDED,
            output_sha256=output_sha256,
            execution_receipt=receipt_sha256,
        ))

    def fail(self, node_id: str, *, expected_version: int,
             effect_unknown: bool = False) -> "TaskGraph":
        current = self.node(node_id)
        if current.state is not TaskState.IN_PROGRESS:
            raise PlanHold("failure requires an active task")
        if type(effect_unknown) is not bool:
            raise PlanHold("typed uncertainty flag required")
        next_state = TaskState.UNKNOWN if effect_unknown else TaskState.FAILED
        return self._update(node_id, expected_version, current._changed(next_state))

    def cold_recover(self) -> "TaskGraph":
        """Fence in-flight work; never infer an execution did not happen."""
        changed = tuple(
            node._changed(TaskState.UNKNOWN) if node.state is TaskState.IN_PROGRESS
            else node for node in self.nodes
        )
        if changed == self.nodes:
            return self
        return TaskGraph(self.graph_id, changed, self.version + 1, self.scope_sha256)

    def blocked(self) -> tuple[str, ...]:
        index = self.index
        bad = set()
        for node_id in self.topological_order():
            node = index[node_id]
            if node.state in _TERMINAL and node.state is not TaskState.SUCCEEDED:
                bad.add(node_id)
            elif any(d in bad for d in node.dependencies):
                bad.add(node_id)
        return tuple(sorted(bad))

    @property
    def all_succeeded(self) -> bool:
        return all(node.state is TaskState.SUCCEEDED for node in self.nodes)


__all__ = ["PlanHold", "TaskState", "TaskNode", "TaskGraph"]
