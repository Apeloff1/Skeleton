"""Capability and execution policy for the Jeeves agent runtime."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .tools import ToolGrant, ToolSpec
from .types import (
    AgentContractError,
    Budget,
    Decision,
    Goal,
    RiskTier,
    Usage,
    finite_number,
    json_safe,
    probability,
    require_id,
)


@dataclass(frozen=True, slots=True)
class PolicyContext:
    run_id: str
    user_id: str
    goal: Goal
    usage: Usage
    budget: Budget
    started_at: float
    confirmed_actions: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        object.__setattr__(self, "user_id", require_id("user_id", self.user_id))
        if not isinstance(self.goal, Goal):
            raise AgentContractError("goal must be Goal")
        if not isinstance(self.usage, Usage):
            raise AgentContractError("usage must be Usage")
        if not isinstance(self.budget, Budget):
            raise AgentContractError("budget must be Budget")
        started = finite_number("started_at", self.started_at)
        if started < 0:
            raise AgentContractError("started_at must be non-negative")
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "confirmed_actions", tuple(require_id("confirmed_action", item) for item in self.confirmed_actions))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    decision: Decision
    reason: str
    policy_id: str
    risk: RiskTier | None = None
    required_confirmation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, Decision):
            object.__setattr__(self, "decision", Decision(str(self.decision)))
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise AgentContractError("policy reason must be non-empty")
        object.__setattr__(self, "reason", self.reason.strip()[:4096])
        object.__setattr__(self, "policy_id", require_id("policy_id", self.policy_id))
        if self.risk is not None and not isinstance(self.risk, RiskTier):
            object.__setattr__(self, "risk", RiskTier(str(self.risk)))
        if self.required_confirmation_id is not None:
            object.__setattr__(self, "required_confirmation_id", require_id("required_confirmation_id", self.required_confirmation_id))


class ExecutionPolicy:
    policy_id = "jeeves-default-v1"

    def __init__(
        self,
        *,
        allow_risks: Sequence[RiskTier] = (RiskTier.READ_ONLY, RiskTier.REVERSIBLE),
        confirm_risks: Sequence[RiskTier] = (RiskTier.MUTATING, RiskTier.EXTERNAL),
        deny_risks: Sequence[RiskTier] = (RiskTier.HIGH_IMPACT,),
        maximum_tool_timeout_seconds: float = 60.0,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._allow = frozenset(risk if isinstance(risk, RiskTier) else RiskTier(str(risk)) for risk in allow_risks)
        self._confirm = frozenset(risk if isinstance(risk, RiskTier) else RiskTier(str(risk)) for risk in confirm_risks)
        self._deny = frozenset(risk if isinstance(risk, RiskTier) else RiskTier(str(risk)) for risk in deny_risks)
        if (self._allow & self._confirm) or (self._allow & self._deny) or (self._confirm & self._deny):
            raise AgentContractError("risk policy sets must not overlap")
        timeout = finite_number("maximum_tool_timeout_seconds", maximum_tool_timeout_seconds)
        if timeout <= 0:
            raise AgentContractError("maximum tool timeout must be positive")
        if not callable(clock) or not callable(monotonic):
            raise AgentContractError("policy clocks must be callable")
        self._max_timeout = timeout
        self._clock = clock
        self._monotonic = monotonic

    def check_budget(self, context: PolicyContext, *, now: float | None = None) -> PolicyDecision:
        now = self._monotonic() if now is None else finite_number("now", now)
        elapsed = max(0.0, now - context.started_at)
        if context.usage.steps >= context.budget.max_steps:
            return PolicyDecision(Decision.DENY, "step budget exhausted", self.policy_id)
        if context.usage.model_calls >= context.budget.max_model_calls:
            return PolicyDecision(Decision.DENY, "model-call budget exhausted", self.policy_id)
        if context.usage.tool_calls >= context.budget.max_tool_calls:
            return PolicyDecision(Decision.DENY, "tool-call budget exhausted", self.policy_id)
        if context.usage.total_tokens >= context.budget.max_tokens:
            return PolicyDecision(Decision.DENY, "token budget exhausted", self.policy_id)
        if elapsed >= context.budget.max_wall_seconds:
            return PolicyDecision(Decision.DENY, "wall-clock budget exhausted", self.policy_id)
        return PolicyDecision(Decision.ALLOW, "budget available", self.policy_id)

    def check_tool(
        self,
        context: PolicyContext,
        spec: ToolSpec,
        arguments: Mapping[str, Any],
        grants: Sequence[ToolGrant],
    ) -> PolicyDecision:
        budget = self.check_budget(context)
        if budget.decision is not Decision.ALLOW:
            return budget
        if spec.timeout_seconds > self._max_timeout:
            return PolicyDecision(
                Decision.DENY,
                "tool timeout exceeds runtime policy",
                self.policy_id,
                risk=spec.risk,
            )
        if spec.risk in self._deny:
            return PolicyDecision(
                Decision.DENY,
                f"risk tier {spec.risk.value} is denied",
                self.policy_id,
                risk=spec.risk,
            )
        active_grant = any(
            grant.permits(spec, arguments, now=self._clock())
            for grant in grants
        )
        if not active_grant:
            return PolicyDecision(
                Decision.DENY,
                "no explicit capability grant permits this call",
                self.policy_id,
                risk=spec.risk,
            )
        if spec.risk in self._confirm:
            confirmation_id = f"confirm:{spec.name}:{context.run_id}"
            if confirmation_id not in context.confirmed_actions:
                return PolicyDecision(
                    Decision.REQUIRE_CONFIRMATION,
                    f"risk tier {spec.risk.value} requires explicit confirmation",
                    self.policy_id,
                    risk=spec.risk,
                    required_confirmation_id=confirmation_id,
                )
        if spec.risk in self._allow or spec.risk in self._confirm:
            return PolicyDecision(
                Decision.ALLOW,
                "tool call is permitted by capability and risk policy",
                self.policy_id,
                risk=spec.risk,
            )
        return PolicyDecision(
            Decision.DENY,
            "risk tier has no configured policy",
            self.policy_id,
            risk=spec.risk,
        )


@dataclass(frozen=True, slots=True)
class ConfidencePolicy:
    answer_threshold: float = 0.55
    action_threshold: float = 0.7
    high_impact_threshold: float = 0.9

    def __post_init__(self) -> None:
        values = [
            probability("answer_threshold", self.answer_threshold),
            probability("action_threshold", self.action_threshold),
            probability("high_impact_threshold", self.high_impact_threshold),
        ]
        if not values[0] <= values[1] <= values[2]:
            raise AgentContractError("confidence thresholds must be non-decreasing")
        object.__setattr__(self, "answer_threshold", values[0])
        object.__setattr__(self, "action_threshold", values[1])
        object.__setattr__(self, "high_impact_threshold", values[2])

    def threshold_for(self, risk: RiskTier | None) -> float:
        if risk is None or risk is RiskTier.READ_ONLY:
            return self.answer_threshold
        if risk in {RiskTier.REVERSIBLE, RiskTier.MUTATING, RiskTier.EXTERNAL}:
            return self.action_threshold
        return self.high_impact_threshold

    def allows(self, confidence: float, risk: RiskTier | None = None) -> bool:
        return probability("confidence", confidence) >= self.threshold_for(risk)


class CompositePolicy:
    """Apply policies in order, with DENY > CONFIRM > DEFER > ALLOW precedence."""

    def __init__(self, policies: Sequence[ExecutionPolicy]) -> None:
        if not policies:
            raise ValueError("at least one execution policy is required")
        self._policies = tuple(policies)

    def check_tool(
        self,
        context: PolicyContext,
        spec: ToolSpec,
        arguments: Mapping[str, Any],
        grants: Sequence[ToolGrant],
    ) -> PolicyDecision:
        decisions = [policy.check_tool(context, spec, arguments, grants) for policy in self._policies]
        precedence = {
            Decision.ALLOW: 0,
            Decision.DEFER: 1,
            Decision.REQUIRE_CONFIRMATION: 2,
            Decision.DENY: 3,
        }
        return max(decisions, key=lambda decision: precedence[decision.decision])
