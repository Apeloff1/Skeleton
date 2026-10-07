"""Closed-loop execution planning with evidence-bound recovery learning."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Iterable, Literal

from .model import RepositoryModel
from .workgraph import WorkGraph, build_work_graph

Phase = Literal["prepare", "modify", "verify", "unlock"]
Outcome = Literal["success", "failed", "blocked", "stale"]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_OBSERVATIONS = 256


@dataclass(frozen=True, slots=True)
class ExecutionObservation:
    ordinal: int
    step_identity: str
    work_identity: str
    phase: Phase
    outcome: Outcome
    evidence_digest: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int) or self.ordinal < 1:
            raise ValueError("observation ordinal must be positive")
        for name, value in (
            ("step_identity", self.step_identity),
            ("work_identity", self.work_identity),
        ):
            if not isinstance(value, str) or not value or len(value) > 512:
                raise ValueError(f"{name} must be non-empty bounded text")
            if any(ord(ch) < 32 for ch in value):
                raise ValueError(f"{name} contains control characters")
        if self.phase not in {"prepare", "modify", "verify", "unlock"}:
            raise ValueError("invalid execution phase")
        if self.outcome not in {"success", "failed", "blocked", "stale"}:
            raise ValueError("invalid execution outcome")
        if self.evidence_digest and _SHA256.fullmatch(self.evidence_digest) is None:
            raise ValueError("evidence_digest must be canonical lowercase sha256")

    def as_dict(self) -> dict[str, object]:
        return {
            "ordinal": self.ordinal,
            "step_identity": self.step_identity,
            "work_identity": self.work_identity,
            "phase": self.phase,
            "outcome": self.outcome,
            "evidence_digest": self.evidence_digest or None,
        }


@dataclass(frozen=True, slots=True)
class PlanStep:
    identity: str
    phase: Phase
    action: str
    depends_on: tuple[str, ...] = ()
    verification_paths: tuple[str, ...] = ()
    work_identity: str = ""
    attempt: int = 1
    recovery_hint: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 1:
            raise ValueError("attempt must be positive")

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "phase": self.phase,
            "action": self.action,
            "depends_on": list(self.depends_on),
            "verification_paths": list(self.verification_paths),
            "work_identity": self.work_identity,
            "attempt": self.attempt,
            "recovery_hint": self.recovery_hint or None,
        }


@dataclass(frozen=True, slots=True)
class ExecutionState:
    completed_steps: tuple[str, ...] = ()
    failed_work: tuple[str, ...] = ()
    verified_work: tuple[str, ...] = ()
    released_work: tuple[str, ...] = ()
    stale: bool = False
    observations: tuple[ExecutionObservation, ...] = ()

    def __post_init__(self) -> None:
        if len(self.observations) > _MAX_OBSERVATIONS:
            raise ValueError(f"execution observations exceed {_MAX_OBSERVATIONS}")
        previous = 0
        for observation in self.observations:
            if not isinstance(observation, ExecutionObservation):
                raise TypeError("observations must contain ExecutionObservation values")
            if observation.ordinal <= previous:
                raise ValueError("execution observation ordinals must increase strictly")
            previous = observation.ordinal

    def work_history(self, work_identity: str) -> tuple[ExecutionObservation, ...]:
        return tuple(item for item in self.observations if item.work_identity == work_identity)

    def learning_surface(self, *, limit: int = 16) -> tuple[dict[str, object], ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 64:
            raise ValueError("limit must be in [1,64]")
        grouped: dict[str, dict[str, object]] = {}
        failed = set(self.failed_work)
        for item in self.observations:
            row = grouped.setdefault(
                item.work_identity,
                {
                    "work_identity": item.work_identity,
                    "observations": 0,
                    "successes": 0,
                    "failures": 0,
                    "blocked": 0,
                    "stale": 0,
                    "evidence_bound": 0,
                    "last_phase": item.phase,
                    "last_outcome": item.outcome,
                    "last_evidence_digest": None,
                    "last_ordinal": item.ordinal,
                    "unresolved_failure": item.work_identity in failed,
                },
            )
            row["observations"] = int(row["observations"]) + 1
            if item.outcome == "success":
                row["successes"] = int(row["successes"]) + 1
            elif item.outcome == "failed":
                row["failures"] = int(row["failures"]) + 1
            elif item.outcome == "blocked":
                row["blocked"] = int(row["blocked"]) + 1
            else:
                row["stale"] = int(row["stale"]) + 1
            if item.evidence_digest:
                row["evidence_bound"] = int(row["evidence_bound"]) + 1
                row["last_evidence_digest"] = item.evidence_digest
            row["last_phase"] = item.phase
            row["last_outcome"] = item.outcome
            row["last_ordinal"] = item.ordinal
            row["unresolved_failure"] = item.work_identity in failed
        rows = list(grouped.values())
        rows.sort(
            key=lambda row: (
                not bool(row["unresolved_failure"]),
                -int(row["failures"]),
                -int(row["blocked"]),
                -int(row["last_ordinal"]),
                str(row["work_identity"]),
            )
        )
        return tuple(rows[:limit])

    def as_dict(self) -> dict[str, object]:
        return {
            "completed_steps": list(self.completed_steps),
            "failed_work": list(self.failed_work),
            "verified_work": list(self.verified_work),
            "released_work": list(self.released_work),
            "stale": self.stale,
            "observations": [item.as_dict() for item in self.observations],
            "learning_surface": list(self.learning_surface()),
        }


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    repository_fingerprint: str
    steps: tuple[PlanStep, ...]
    ready_work: tuple[str, ...]
    blocked_work: tuple[str, ...]
    state: ExecutionState = ExecutionState()
    graph_fingerprint: str = ""
    parallel_batches: tuple[tuple[str, ...], ...] = ()
    _steps_by_identity: dict[str, PlanStep] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        by: dict[str, PlanStep] = {}
        for step in self.steps:
            if step.identity in by:
                raise ValueError(f"duplicate execution step: {step.identity}")
            by[step.identity] = step
        historically_completed = set(self.state.completed_steps)
        for step in self.steps:
            if any(
                dependency not in by and dependency not in historically_completed
                for dependency in step.depends_on
            ):
                raise ValueError(f"unknown step dependency for {step.identity}")
        object.__setattr__(self, "_steps_by_identity", by)

    @property
    def definition_fingerprint(self) -> str:
        payload = {
            "repository_fingerprint": self.repository_fingerprint,
            "steps": [step.as_dict() for step in self.steps],
            "ready_work": list(self.ready_work),
            "blocked_work": list(self.blocked_work),
            "parallel_batches": [list(batch) for batch in self.parallel_batches],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @property
    def fingerprint(self) -> str:
        payload = {
            "definition": self.definition_fingerprint,
            "state": self.state.as_dict(),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            "repository_fingerprint": self.repository_fingerprint,
            "plan_fingerprint": self.fingerprint,
            "definition_fingerprint": self.definition_fingerprint,
            "steps": [step.as_dict() for step in self.steps],
            "ready_work": list(self.ready_work),
            "blocked_work": list(self.blocked_work),
            "state": self.state.as_dict(),
            "graph_fingerprint": self.graph_fingerprint,
            "parallel_batches": [list(batch) for batch in self.parallel_batches],
        }


def _step_work_identity(step: PlanStep) -> str:
    if step.work_identity:
        return step.work_identity
    prefix, separator, _ = step.identity.rpartition(":")
    return prefix if separator and prefix else step.identity


def _normalize_evidence_digest(evidence_digest: str | None) -> str:
    if evidence_digest is None or evidence_digest == "":
        return ""
    if not isinstance(evidence_digest, str):
        raise TypeError("evidence_digest must be text")
    if _SHA256.fullmatch(evidence_digest) is None:
        raise ValueError("evidence_digest must be canonical lowercase sha256")
    return evidence_digest


def _append_observation(
    state: ExecutionState,
    step: PlanStep,
    outcome: Outcome,
    evidence_digest: str,
) -> tuple[ExecutionObservation, ...]:
    ordinal = max((item.ordinal for item in state.observations), default=0) + 1
    observation = ExecutionObservation(
        ordinal,
        step.identity,
        _step_work_identity(step),
        step.phase,
        outcome,
        evidence_digest,
    )
    return (state.observations + (observation,))[-_MAX_OBSERVATIONS:]


def _execution_state(
    completed: set[str],
    failed: set[str],
    verified: set[str],
    released: set[str],
    *,
    stale: bool,
    observations: tuple[ExecutionObservation, ...],
) -> ExecutionState:
    return ExecutionState(
        tuple(sorted(completed)),
        tuple(sorted(failed)),
        tuple(sorted(verified)),
        tuple(sorted(released)),
        stale,
        observations,
    )


def _stale_plan(
    plan: ExecutionPlan,
    completed: set[str],
    failed: set[str],
    verified: set[str],
    released: set[str],
    *,
    step: PlanStep | None = None,
    evidence_digest: str = "",
) -> ExecutionPlan:
    observations = plan.state.observations
    if step is not None:
        observations = _append_observation(plan.state, step, "stale", evidence_digest)
    state = _execution_state(
        completed,
        failed,
        verified,
        released,
        stale=True,
        observations=observations,
    )
    return ExecutionPlan(
        plan.repository_fingerprint,
        plan.steps,
        (),
        plan.blocked_work,
        state,
        plan.graph_fingerprint,
        plan.parallel_batches,
    )


def advance_execution(
    plan: ExecutionPlan,
    *,
    step_identity: str,
    outcome: Outcome,
    repository_fingerprint: str,
    expected_plan_fingerprint: str | None = None,
    evidence_digest: str | None = None,
) -> ExecutionPlan:
    """Apply one observed transition and retain bounded evidence for recovery."""
    if outcome not in {"success", "failed", "blocked", "stale"}:
        raise ValueError("invalid execution outcome")
    evidence = _normalize_evidence_digest(evidence_digest)
    if expected_plan_fingerprint is not None and expected_plan_fingerprint != plan.fingerprint:
        raise ValueError("execution plan fingerprint mismatch")
    if plan.state.stale:
        raise ValueError("stale execution plan must be replanned before execution")

    step = plan._steps_by_identity.get(step_identity)
    completed = set(plan.state.completed_steps)
    failed = set(plan.state.failed_work)
    verified = set(plan.state.verified_work)
    released = set(plan.state.released_work)

    if repository_fingerprint != plan.repository_fingerprint:
        return _stale_plan(
            plan,
            completed,
            failed,
            verified,
            released,
            step=step,
            evidence_digest=evidence,
        )
    if step is None:
        raise ValueError("unknown execution step")
    if step.identity in completed:
        raise ValueError("execution step already completed")
    if any(dependency not in completed for dependency in step.depends_on):
        raise ValueError("execution step prerequisites are incomplete")

    if outcome == "stale":
        return _stale_plan(
            plan,
            completed,
            failed,
            verified,
            released,
            step=step,
            evidence_digest=evidence,
        )

    observations = _append_observation(plan.state, step, outcome, evidence)
    if outcome == "blocked":
        state = _execution_state(
            completed,
            failed,
            verified,
            released,
            stale=False,
            observations=observations,
        )
        return ExecutionPlan(
            plan.repository_fingerprint,
            plan.steps,
            plan.ready_work,
            plan.blocked_work,
            state,
            plan.graph_fingerprint,
            plan.parallel_batches,
        )

    if outcome == "success":
        completed.add(step.identity)
        if step.phase == "verify":
            work_identity = _step_work_identity(step)
            verified.add(work_identity)
            failed.discard(work_identity)
        elif step.phase == "unlock":
            work_identity = _step_work_identity(step)
            if work_identity not in verified:
                raise ValueError("work must be verified before unlock")
            released.add(work_identity)
            failed.discard(work_identity)
        elif any(
            item.step_identity == step.identity and item.outcome == "failed"
            for item in plan.state.observations
        ):
            failed.discard(_step_work_identity(step))
    else:
        work_identity = _step_work_identity(step)
        failed.add(work_identity)
        if step.phase != "unlock":
            verified.discard(work_identity)
        released.discard(work_identity)

    state = _execution_state(
        completed,
        failed,
        verified,
        released,
        stale=False,
        observations=observations,
    )
    return ExecutionPlan(
        plan.repository_fingerprint,
        plan.steps,
        plan.ready_work,
        plan.blocked_work,
        state,
        plan.graph_fingerprint,
        plan.parallel_batches,
    )


def _counterfactual_order(
    graph: WorkGraph,
    ready: tuple,
    completed: set[str],
) -> tuple:
    surface = graph.counterfactual_surface(
        completed,
        limit=max(1, len(ready)),
    ) if ready else ()
    scores = {
        row["identity"]: (
            row["pressure_reduction"],
            row["newly_unblocked_count"],
            row["risk_adjusted_influence"],
            row["strategic_value"],
        )
        for row in surface
    }
    return tuple(
        sorted(
            ready,
            key=lambda node: (
                scores.get(node.identity, (0, 0, 0, 0))[0],
                scores.get(node.identity, (0, 0, 0, 0))[1],
                scores.get(node.identity, (0, 0, 0, 0))[2],
                scores.get(node.identity, (0, 0, 0, 0))[3],
                node.identity,
            ),
            reverse=True,
        )
    )


def _recovery_profile(
    state: ExecutionState,
    work_identity: str,
) -> tuple[int, str]:
    history = state.work_history(work_identity)
    failures = sum(item.outcome == "failed" for item in history)
    blocked = sum(item.outcome == "blocked" for item in history)
    if not history or not (failures or blocked):
        return 1, ""
    evidence_bound = sum(bool(item.evidence_digest) for item in history)
    last = history[-1]
    attempt = failures + 1
    hint = (
        f"Prior observations: failures={failures}, blocked={blocked}, "
        f"evidence_bound={evidence_bound}/{len(history)}, "
        f"last={last.phase}:{last.outcome}. Reuse valid evidence, isolate the "
        "last failing boundary, and change the smallest causal surface before retry."
    )
    return attempt, hint


def _work_steps(node, state: ExecutionState) -> tuple[PlanStep, ...]:
    prepare, modify, verify, unlock = (
        f"{node.identity}:{phase}"
        for phase in ("prepare", "modify", "verify", "unlock")
    )
    attempt, recovery_hint = _recovery_profile(state, node.identity)
    prepare_action = (
        f"Inspect evidence and establish the bounded change scope for {node.identity}."
    )
    verify_action = (
        "Run the smallest relevant verification surface before considering the work complete."
    )
    if recovery_hint:
        prepare_action = f"{prepare_action} {recovery_hint}"
        verify_action = (
            f"{verify_action} Compare the new result with the retained recovery evidence."
        )
    steps = (
        PlanStep(
            prepare,
            "prepare",
            prepare_action,
            work_identity=node.identity,
            attempt=attempt,
            recovery_hint=recovery_hint,
        ),
        PlanStep(
            modify,
            "modify",
            node.objective,
            (prepare,),
            work_identity=node.identity,
            attempt=attempt,
            recovery_hint=recovery_hint,
        ),
        PlanStep(
            verify,
            "verify",
            verify_action,
            (modify,),
            node.verification_paths,
            node.identity,
            attempt,
            recovery_hint,
        ),
        PlanStep(
            unlock,
            "unlock",
            "Release the verified work and recompute downstream readiness.",
            (verify,),
            work_identity=node.identity,
            attempt=attempt,
            recovery_hint=recovery_hint,
        ),
    )
    completed = set(state.completed_steps)
    return tuple(step for step in steps if step.identity not in completed)


def build_execution_plan(
    model: RepositoryModel,
    *,
    completed: Iterable[str] = (),
    active_conflicts: Iterable[str] = (),
    limit: int = 8,
    state: ExecutionState | None = None,
    retry_failed: bool = False,
    graph: WorkGraph | None = None,
) -> ExecutionPlan:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 64:
        raise ValueError("limit must be in [1,64]")
    graph = graph or build_work_graph(model, limit=max(limit, 32))
    inherited = state or ExecutionState()
    if inherited.stale:
        raise ValueError("stale execution state must be replanned before reuse")
    completed_set = set(completed) | set(inherited.released_work)
    conflict_keys = tuple(active_conflicts)
    ready = graph.ready(completed_set, conflict_keys, limit=limit)
    failed = set(inherited.failed_work)
    if not retry_failed:
        ready = tuple(node for node in ready if node.identity not in failed)
    ready = _counterfactual_order(graph, ready, completed_set)
    ready_ids = {node.identity for node in ready}

    steps: list[PlanStep] = []
    for node in ready:
        steps.extend(_work_steps(node, inherited))

    blocked = tuple(
        node.identity
        for node in graph.ordered_nodes
        if node.identity not in ready_ids and node.identity not in completed_set
    )
    eligible_parallel = set(ready_ids)
    raw_batches = graph.safe_parallel_groups(completed_set, limit=min(8, limit))
    batches = tuple(
        filtered
        for group in raw_batches
        if (filtered := tuple(identity for identity in group if identity in eligible_parallel))
    )
    return ExecutionPlan(
        model.fingerprint,
        tuple(steps),
        tuple(node.identity for node in ready),
        blocked,
        inherited,
        graph.fingerprint,
        batches,
    )


def replan_execution(
    model: RepositoryModel,
    previous: ExecutionPlan,
    *,
    active_conflicts: Iterable[str] = (),
    limit: int = 8,
    retry_failed: bool = False,
    graph: WorkGraph | None = None,
) -> ExecutionPlan:
    state = previous.state
    if state.stale:
        state = ExecutionState(observations=state.observations)
    return build_execution_plan(
        model,
        active_conflicts=active_conflicts,
        limit=limit,
        state=state,
        retry_failed=retry_failed,
        graph=graph,
    )


__all__ = [
    "ExecutionObservation",
    "ExecutionPlan",
    "ExecutionState",
    "Outcome",
    "Phase",
    "PlanStep",
    "advance_execution",
    "build_execution_plan",
    "replan_execution",
]
