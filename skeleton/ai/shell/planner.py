"""AI planner that exposes only routed, redacted tool cards to a model."""

from __future__ import annotations

from dataclasses import dataclass
import uuid

from skeleton.shells.ai.budget import AIBudget
from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.model_port import AIModelPort
from skeleton.shells.ai.protocol import AIModelRequest, AIModelResponse
from skeleton.shells.ai.router import AIToolRouter, RoutedTool
from skeleton.shells.ai.types import AIIntent


@dataclass(frozen=True)
class PlanningResult:
    request: AIModelRequest
    response: AIModelResponse
    routed_tools: tuple[RoutedTool, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request.request_id,
            "proposal_id": self.response.proposal.proposal_id,
            "routed_tools": [item.to_dict() for item in self.routed_tools],
        }


class AIPlanner:
    def __init__(
        self,
        model: AIModelPort,
        catalog: AIToolCatalog,
        router: AIToolRouter,
        *,
        policy_fingerprint: str,
        budget: AIBudget | None = None,
        max_tools: int = 32,
    ) -> None:
        if len(policy_fingerprint) != 64:
            raise ValueError("policy_fingerprint must be SHA-256 hex")
        if max_tools <= 0:
            raise ValueError("max_tools must be positive")
        self.model = model
        self.catalog = catalog
        self.router = router
        self.policy_fingerprint = policy_fingerprint
        self.budget = budget or AIBudget()
        self.max_tools = max_tools

    def build_request(
        self,
        intent: AIIntent,
        *,
        prior_observations: tuple[dict[str, object], ...] = (),
        request_id: str | None = None,
    ) -> tuple[AIModelRequest, tuple[RoutedTool, ...]]:
        routed = self.router.route(intent, limit=self.max_tools)
        request = AIModelRequest(
            request_id=request_id or uuid.uuid4().hex,
            intent=intent,
            tool_catalog_digest=self.catalog.digest,
            policy_fingerprint=self.policy_fingerprint,
            tool_cards=tuple(item.card.to_dict() for item in routed),
            prior_observations=prior_observations,
        )
        return request, routed

    def propose(
        self,
        intent: AIIntent,
        *,
        prior_observations: tuple[dict[str, object], ...] = (),
        request_id: str | None = None,
    ) -> PlanningResult:
        request, routed = self.build_request(
            intent,
            prior_observations=prior_observations,
            request_id=request_id,
        )
        response = self.model.propose(request)
        self.budget.model_call(actions=len(response.proposal.actions))
        return PlanningResult(request, response, routed)
