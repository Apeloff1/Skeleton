"""Closed-loop execution planning over repository work candidates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .model import RepositoryModel
from .planner import WorkCandidate
from .workgraph import WorkGraph, WorkNode, build_work_graph


@dataclass(frozen=True, slots=True)
class PlanStep:
    identity: str
    phase: str
    action: str
    depends_on: tuple[str, ...] = ()
    verification_paths: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "phase": self.phase,
            "action": self.action,
            "depends_on": list(self.depends_on),
            "verification_paths": list(self.verification_paths),
        }


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    repository_fingerprint: str
    steps: tuple[PlanStep, ...]
    ready_work: tuple[str, ...]
    blocked_work: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "repository_fingerprint": self.repository_fingerprint,
            "steps": [item.as_dict() for item in self.steps],
            "ready_work": list(self.ready_work),
            "blocked_work": list(self.blocked_work),
        }


def build_execution_plan(
    model: RepositoryModel,
    *,
    completed: Iterable[str] = (),
    active_conflicts: Iterable[str] = (),
    limit: int = 8,
) -> ExecutionPlan:
    graph = build_work_graph(model, limit=max(limit, 32))
    completed_set = set(completed)
    ready = graph.ready(completed_set, active_conflicts, limit=limit)
    ready_ids = {node.identity for node in ready}
    steps: list[PlanStep] = []

    for node in ready:
        prepare = f"{node.identity}:prepare"
        modify = f"{node.identity}:modify"
        verify = f"{node.identity}:verify"
        unlock = f"{node.identity}:unlock"
        steps.extend((
            PlanStep(prepare, "prepare", f"Inspect evidence and establish the bounded change scope for {node.identity}."),
            PlanStep(modify, "modify", node.objective, (prepare,)),
            PlanStep(verify, "verify", "Run the smallest relevant verification surface before considering the work complete.", (modify,), node.verification_paths),
            PlanStep(unlock, "unlock", "Recompute downstream readiness from the updated repository state.", (verify,)),
        ))

    blocked = tuple(
        node.identity for node in graph._ordered_nodes
        if node.identity not in ready_ids and node.identity not in completed_set
    )
    return ExecutionPlan(
        repository_fingerprint=model.fingerprint,
        steps=tuple(steps),
        ready_work=tuple(node.identity for node in ready),
        blocked_work=blocked,
    )
