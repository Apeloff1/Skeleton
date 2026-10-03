"""Closed-loop execution planning with explicit state transitions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from .model import RepositoryModel
from .workgraph import build_work_graph

Phase = Literal["prepare", "modify", "verify", "unlock"]
Outcome = Literal["success", "failed", "blocked", "stale"]


@dataclass(frozen=True, slots=True)
class PlanStep:
    identity: str
    phase: Phase
    action: str
    depends_on: tuple[str, ...] = ()
    verification_paths: tuple[str, ...] = ()
    work_identity: str = ""

    def as_dict(self) -> dict[str, object]:
        return {"identity": self.identity, "phase": self.phase, "action": self.action,
                "depends_on": list(self.depends_on), "verification_paths": list(self.verification_paths),
                "work_identity": self.work_identity}


@dataclass(frozen=True, slots=True)
class ExecutionState:
    completed_steps: tuple[str, ...] = ()
    failed_work: tuple[str, ...] = ()
    verified_work: tuple[str, ...] = ()
    stale: bool = False

    def as_dict(self) -> dict[str, object]:
        return {"completed_steps": list(self.completed_steps), "failed_work": list(self.failed_work),
                "verified_work": list(self.verified_work), "stale": self.stale}


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    repository_fingerprint: str
    steps: tuple[PlanStep, ...]
    ready_work: tuple[str, ...]
    blocked_work: tuple[str, ...]
    state: ExecutionState = ExecutionState()

    def as_dict(self) -> dict[str, object]:
        return {"repository_fingerprint": self.repository_fingerprint,
                "steps": [item.as_dict() for item in self.steps],
                "ready_work": list(self.ready_work), "blocked_work": list(self.blocked_work),
                "state": self.state.as_dict()}


def advance_execution(plan: ExecutionPlan, *, step_identity: str, outcome: Outcome,
                      repository_fingerprint: str) -> ExecutionPlan:
    """Apply one observed result; reject invalid transitions and stale state."""
    if repository_fingerprint != plan.repository_fingerprint:
        return ExecutionPlan(plan.repository_fingerprint, plan.steps, (), plan.blocked_work,
                             ExecutionState(plan.state.completed_steps, plan.state.failed_work,
                                            plan.state.verified_work, True))
    step = next((item for item in plan.steps if item.identity == step_identity), None)
    if step is None:
        raise ValueError("unknown execution step")
    completed = set(plan.state.completed_steps)
    failed = set(plan.state.failed_work)
    verified = set(plan.state.verified_work)
    if step.identity in completed:
        raise ValueError("execution step already completed")
    if any(dependency not in completed for dependency in step.depends_on):
        raise ValueError("execution step prerequisites are incomplete")
    if outcome == "success":
        completed.add(step.identity)
        if step.phase == "verify":
            verified.add(step.work_identity)
    elif outcome == "failed":
        failed.add(step.work_identity)
    elif outcome == "stale":
        return ExecutionPlan(plan.repository_fingerprint, plan.steps, (), plan.blocked_work,
                             ExecutionState(tuple(sorted(completed)), tuple(sorted(failed)),
                                            tuple(sorted(verified)), True))
    elif outcome == "blocked":
        return plan
    return ExecutionPlan(plan.repository_fingerprint, plan.steps, plan.ready_work, plan.blocked_work,
                         ExecutionState(tuple(sorted(completed)), tuple(sorted(failed)),
                                        tuple(sorted(verified)), False))


def build_execution_plan(model: RepositoryModel, *, completed: Iterable[str] = (),
                         active_conflicts: Iterable[str] = (), limit: int = 8) -> ExecutionPlan:
    graph = build_work_graph(model, limit=max(limit, 32))
    completed_set = set(completed)
    ready = graph.ready(completed_set, active_conflicts, limit=limit)
    ready_ids = {node.identity for node in ready}
    steps: list[PlanStep] = []
    for node in ready:
        prepare, modify, verify, unlock = (f"{node.identity}:{phase}" for phase in ("prepare", "modify", "verify", "unlock"))
        steps.extend((
            PlanStep(prepare, "prepare", f"Inspect evidence and establish the bounded change scope for {node.identity}.", work_identity=node.identity),
            PlanStep(modify, "modify", node.objective, (prepare,), work_identity=node.identity),
            PlanStep(verify, "verify", "Run the smallest relevant verification surface before considering the work complete.", (modify,), node.verification_paths, node.identity),
            PlanStep(unlock, "unlock", "Recompute downstream readiness from the updated repository state.", (verify,), work_identity=node.identity),
        ))
    blocked = tuple(node.identity for node in graph._ordered_nodes if node.identity not in ready_ids and node.identity not in completed_set)
    return ExecutionPlan(model.fingerprint, tuple(steps), tuple(node.identity for node in ready), blocked)


__all__ = ["ExecutionPlan", "ExecutionState", "Outcome", "Phase", "PlanStep", "advance_execution", "build_execution_plan"]
