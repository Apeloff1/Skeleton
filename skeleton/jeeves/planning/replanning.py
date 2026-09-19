from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .models import Goal, Plan, PlanState, RiskTier, Step, fingerprint, topological_order


class ReplanReason(str, Enum):
    EVIDENCE_GAP = "evidence_gap"
    CONTRADICTION = "contradiction"
    RESOURCE_LIMIT = "resource_limit"
    POLICY_CHANGE = "policy_change"
    DEPENDENCY_FAILURE = "dependency_failure"
    EXTERNAL_BLOCK = "external_block"


@dataclass(frozen=True, slots=True)
class Observation:
    source: str
    reason: ReplanReason
    detail: str
    severity: int = 50

    def __post_init__(self) -> None:
        if not self.source or len(self.source) > 256:
            raise ValueError("invalid observation source")
        if not self.detail or len(self.detail) > 4096:
            raise ValueError("invalid observation detail")
        if not 0 <= self.severity <= 100:
            raise ValueError("severity out of bounds")


@dataclass(frozen=True, slots=True)
class ReplanProposal:
    base_plan_id: str
    removed_steps: tuple[str, ...]
    added_steps: tuple[Step, ...]
    rationale: tuple[str, ...]
    confidence: float

    def __post_init__(self) -> None:
        if not self.base_plan_id or len(self.base_plan_id) != 64:
            raise ValueError("invalid base plan id")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence out of bounds")
        if len(self.rationale) > 64:
            raise ValueError("too much rationale")


def collect_observations(observations: Iterable[Observation]) -> tuple[Observation, ...]:
    result = tuple(observations)
    if not result:
        raise ValueError("at least one observation is required")
    return tuple(sorted(result, key=lambda x: (-x.severity, x.source, x.detail)))


def propose(plan: Plan, observations: Iterable[Observation]) -> ReplanProposal:
    obs = collect_observations(observations)
    remove: set[str] = set()
    added: list[Step] = []
    rationale: list[str] = []
    for item in obs:
        rationale.append(f"{item.reason.value}: {item.detail}")
        if item.reason in {ReplanReason.DEPENDENCY_FAILURE, ReplanReason.EXTERNAL_BLOCK}:
            remove.update(step.name for step in plan.steps if item.source == step.name)
        if item.reason is ReplanReason.EVIDENCE_GAP:
            for step in plan.steps:
                if step.name == item.source and step.evidence_required:
                    added.append(Step(name=f"verify:{step.name}", action="collect bounded evidence", depends_on=step.depends_on, evidence_required=True, risk=RiskTier.MEDIUM))
    added_names = {step.name for step in plan.steps}
    added = [step for step in added if step.name not in added_names and step.name not in remove]
    confidence = min(1.0, sum(item.severity for item in obs) / (100 * len(obs)))
    return ReplanProposal(plan.id, tuple(sorted(remove)), tuple(added), tuple(rationale), confidence)


def apply_proposal(plan: Plan, proposal: ReplanProposal) -> Plan:
    if proposal.base_plan_id != plan.id:
        raise ValueError("proposal does not target supplied plan")
    kept = [step for step in plan.steps if step.name not in set(proposal.removed_steps)]
    names = {step.name for step in kept}
    for step in proposal.added_steps:
        if step.name in names:
            raise ValueError("replan introduces duplicate step")
        kept.append(step)
        names.add(step.name)
    candidate = Plan(goal=plan.goal, steps=tuple(kept), state=PlanState.DRAFT, assumptions=plan.assumptions, labels=plan.labels + ("replanned",))
    topological_order(candidate)
    return candidate


def proposal_fingerprint(proposal: ReplanProposal) -> str:
    return fingerprint({"base": proposal.base_plan_id, "removed": proposal.removed_steps, "added": tuple(step.id for step in proposal.added_steps), "rationale": proposal.rationale, "confidence": proposal.confidence})
