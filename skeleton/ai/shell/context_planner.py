"""Context-provenance-aware wrapper around AIPlanner."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.context_policy import ContextPolicyDecision, ContextPolicyEngine
from skeleton.shells.ai.context_provenance import ContextBundle
from skeleton.shells.ai.planner import AIPlanner, PlanningResult
from skeleton.shells.ai.types import AIIntent


@dataclass(frozen=True)
class ContextPlanningResult:
    planning: PlanningResult
    context_digest: str
    context_policy: ContextPolicyDecision

    def to_dict(self) -> dict[str, object]:
        return {
            "planning": self.planning.to_dict(),
            "context_digest": self.context_digest,
            "context_policy": self.context_policy.to_dict(),
        }


class ContextAwareAIPlanner:
    """Labels context origin and rejects secret or over-budget model context."""

    def __init__(
        self,
        planner: AIPlanner,
        *,
        context_policy: ContextPolicyEngine | None = None,
    ) -> None:
        self.planner = planner
        self.context_policy = context_policy or ContextPolicyEngine()

    def propose(
        self,
        intent: AIIntent,
        context: ContextBundle,
        *,
        prior_observations: tuple[dict[str, object], ...] = (),
    ) -> ContextPlanningResult:
        decision = self.context_policy.require(context)
        model_context = context.to_model_payload()
        observation = {
            "kind": "provenance_context",
            "context_digest": context.digest,
            "items": list(model_context),
        }
        planning = self.planner.propose(
            intent,
            prior_observations=prior_observations + (observation,),
        )
        return ContextPlanningResult(
            planning,
            context.digest,
            decision,
        )
