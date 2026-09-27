"""Deterministic reasoning progress and stopping authority for P1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any

from skeleton.contracts.canonical import EvidenceRef
from skeleton.frontier.contracts import stable_content_digest
from skeleton.intelligence.strategy_registry import (
    ReasoningBudget,
    ReasoningStrategyError,
    ReasoningStrategyRegistry,
    StrategySelection,
)


class StopAction(str, Enum):
    CONTINUE = "continue"
    STOP_SUCCESS = "stop_success"
    STOP_BUDGET = "stop_budget"
    STOP_DIMINISHING_RETURNS = "stop_diminishing_returns"
    ABSTAIN_UNCERTAIN = "abstain_uncertain"
    ABSTAIN_UNVERIFIED = "abstain_unverified"
    POLICY_VIOLATION = "policy_violation"


_TERMINAL_ACTIONS = {
    StopAction.STOP_SUCCESS,
    StopAction.STOP_BUDGET,
    StopAction.STOP_DIMINISHING_RETURNS,
    StopAction.ABSTAIN_UNCERTAIN,
    StopAction.ABSTAIN_UNVERIFIED,
    StopAction.POLICY_VIOLATION,
}


class CognitiveRuntimeError(ValueError):
    """Reasoning progress cannot be evaluated under the selected policy."""


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CognitiveRuntimeError(
            f"{field} must be a non-negative integer"
        )
    return value


def _finite_nonnegative(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CognitiveRuntimeError(
            f"{field} must be finite and non-negative"
        )
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise CognitiveRuntimeError(
            f"{field} must be finite and non-negative"
        )
    return number


def _unit(value: object, field: str) -> float:
    number = _finite_nonnegative(value, field)
    if number > 1.0:
        raise CognitiveRuntimeError(f"{field} must be within [0, 1]")
    return number


@dataclass(frozen=True, slots=True)
class ReasoningProgress:
    request_id: str
    strategy_id: str
    iterations: int
    candidates: int
    retrieval_rounds: int
    tool_calls: int
    cost: float
    wall_seconds: float
    evidence_gain: float
    value_of_information: float
    uncertainty: float
    completed: bool = False
    verified: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id:
            raise CognitiveRuntimeError("request_id must be non-empty")
        if not isinstance(self.strategy_id, str) or not self.strategy_id:
            raise CognitiveRuntimeError("strategy_id must be non-empty")
        for field in (
            "iterations",
            "candidates",
            "retrieval_rounds",
            "tool_calls",
        ):
            object.__setattr__(
                self,
                field,
                _nonnegative_int(getattr(self, field), field),
            )
        for field in ("cost", "wall_seconds"):
            object.__setattr__(
                self,
                field,
                _finite_nonnegative(getattr(self, field), field),
            )
        for field in (
            "evidence_gain",
            "value_of_information",
            "uncertainty",
        ):
            object.__setattr__(
                self,
                field,
                _unit(getattr(self, field), field),
            )
        if not isinstance(self.completed, bool) or not isinstance(
            self.verified,
            bool,
        ):
            raise CognitiveRuntimeError(
                "completed and verified must be boolean"
            )
        if self.verified and not self.completed:
            raise CognitiveRuntimeError(
                "verified progress must also be completed"
            )

    def usage_dict(self) -> dict[str, Any]:
        return {
            "iterations": self.iterations,
            "candidates": self.candidates,
            "retrieval_rounds": self.retrieval_rounds,
            "tool_calls": self.tool_calls,
            "cost": self.cost,
            "wall_seconds": self.wall_seconds,
        }

    def signal_dict(self) -> dict[str, Any]:
        return {
            "evidence_gain": self.evidence_gain,
            "value_of_information": self.value_of_information,
            "uncertainty": self.uncertainty,
            "completed": self.completed,
            "verified": self.verified,
        }

    @property
    def digest(self) -> str:
        return stable_content_digest(
            {
                "request_id": self.request_id,
                "strategy_id": self.strategy_id,
                "usage": self.usage_dict(),
                "signals": self.signal_dict(),
            }
        )


@dataclass(frozen=True, slots=True)
class StopDecision:
    request_id: str
    strategy_id: str
    action: StopAction
    reason: str
    exceeded_dimensions: tuple[str, ...] = ()
    reached_dimensions: tuple[str, ...] = ()

    @property
    def terminal(self) -> bool:
        return self.action in _TERMINAL_ACTIONS

    @property
    def policy_compliant(self) -> bool:
        return self.action is not StopAction.POLICY_VIOLATION

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "strategy_id": self.strategy_id,
            "action": self.action.value,
            "reason": self.reason,
            "terminal": self.terminal,
            "policy_compliant": self.policy_compliant,
            "exceeded_dimensions": list(self.exceeded_dimensions),
            "reached_dimensions": list(self.reached_dimensions),
        }

    @property
    def digest(self) -> str:
        return stable_content_digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ReasoningPolicyReceipt:
    registry_digest: str
    selection_digest: str
    progress_digest: str
    decision_digest: str
    strategy_id: str
    action: str
    terminal: bool
    policy_compliant: bool
    eligible_for_promotion: bool

    @property
    def receipt_digest(self) -> str:
        return stable_content_digest(self.payload())

    def payload(self) -> dict[str, Any]:
        return {
            "registry_digest": self.registry_digest,
            "selection_digest": self.selection_digest,
            "progress_digest": self.progress_digest,
            "decision_digest": self.decision_digest,
            "strategy_id": self.strategy_id,
            "action": self.action,
            "terminal": self.terminal,
            "policy_compliant": self.policy_compliant,
            "eligible_for_promotion": self.eligible_for_promotion,
        }

    def evidence_ref(self) -> EvidenceRef:
        if not self.eligible_for_promotion:
            raise CognitiveRuntimeError(
                "nonterminal or policy-violating reasoning cannot become "
                "promotion evidence"
            )
        return EvidenceRef(
            source=f"p1:reasoning-stop:{self.strategy_id}",
            digest=self.receipt_digest,
            category="reasoning_strategy_stop",
        )


def _usage_dimensions(
    progress: ReasoningProgress,
) -> tuple[tuple[str, float], ...]:
    return (
        ("iterations", float(progress.iterations)),
        ("candidates", float(progress.candidates)),
        ("retrieval_rounds", float(progress.retrieval_rounds)),
        ("tool_calls", float(progress.tool_calls)),
        ("cost", progress.cost),
        ("wall_seconds", progress.wall_seconds),
    )


def _budget_dimensions(
    budget: ReasoningBudget,
) -> dict[str, float]:
    return {
        "iterations": float(budget.iterations),
        "candidates": float(budget.candidates),
        "retrieval_rounds": float(budget.retrieval_rounds),
        "tool_calls": float(budget.tool_calls),
        "cost": budget.cost,
        "wall_seconds": budget.wall_seconds,
    }


def evaluate_reasoning_progress(
    registry: ReasoningStrategyRegistry,
    selection: StrategySelection,
    progress: ReasoningProgress,
) -> StopDecision:
    """Apply hard budget and evidence/VOI stopping policy deterministically."""

    if not isinstance(registry, ReasoningStrategyRegistry):
        raise TypeError("registry must be ReasoningStrategyRegistry")
    if not isinstance(selection, StrategySelection):
        raise TypeError("selection must be StrategySelection")
    if not isinstance(progress, ReasoningProgress):
        raise TypeError("progress must be ReasoningProgress")
    if selection.registry_digest != registry.digest:
        raise CognitiveRuntimeError("selection registry digest is stale")
    if progress.request_id != selection.request_id:
        raise CognitiveRuntimeError("progress request identity mismatch")
    if progress.strategy_id != selection.strategy_id:
        raise CognitiveRuntimeError("progress strategy identity mismatch")

    strategy = registry.by_id(selection.strategy_id)
    budget = selection.effective_budget
    limits = _budget_dimensions(budget)
    exceeded = tuple(
        name
        for name, used in _usage_dimensions(progress)
        if used > limits[name] + 1e-12
    )
    reached = tuple(
        name
        for name, used in _usage_dimensions(progress)
        if limits[name] > 0.0 and abs(used - limits[name]) <= 1e-12
    )

    if exceeded:
        return StopDecision(
            request_id=progress.request_id,
            strategy_id=progress.strategy_id,
            action=StopAction.POLICY_VIOLATION,
            reason="hard_budget_exceeded",
            exceeded_dimensions=exceeded,
            reached_dimensions=reached,
        )

    if progress.completed:
        if progress.verified:
            return StopDecision(
                request_id=progress.request_id,
                strategy_id=progress.strategy_id,
                action=StopAction.STOP_SUCCESS,
                reason="verified_completion",
                reached_dimensions=reached,
            )
        return StopDecision(
            request_id=progress.request_id,
            strategy_id=progress.strategy_id,
            action=StopAction.ABSTAIN_UNVERIFIED,
            reason="completion_without_verification",
            reached_dimensions=reached,
        )

    if reached:
        return StopDecision(
            request_id=progress.request_id,
            strategy_id=progress.strategy_id,
            action=StopAction.STOP_BUDGET,
            reason="hard_budget_reached",
            reached_dimensions=reached,
        )

    stop = strategy.stop_policy
    if (
        progress.uncertainty >= stop.abstain_uncertainty
        and progress.evidence_gain <= stop.min_evidence_gain
    ):
        return StopDecision(
            request_id=progress.request_id,
            strategy_id=progress.strategy_id,
            action=StopAction.ABSTAIN_UNCERTAIN,
            reason="uncertainty_without_evidence_gain",
        )

    if (
        progress.iterations > 0
        and progress.evidence_gain <= stop.min_evidence_gain
        and progress.value_of_information
        <= stop.min_value_of_information
    ):
        return StopDecision(
            request_id=progress.request_id,
            strategy_id=progress.strategy_id,
            action=StopAction.STOP_DIMINISHING_RETURNS,
            reason="low_evidence_gain_and_value_of_information",
        )

    return StopDecision(
        request_id=progress.request_id,
        strategy_id=progress.strategy_id,
        action=StopAction.CONTINUE,
        reason="bounded_progress_has_remaining_value",
    )


def build_reasoning_policy_receipt(
    registry: ReasoningStrategyRegistry,
    selection: StrategySelection,
    progress: ReasoningProgress,
) -> ReasoningPolicyReceipt:
    decision = evaluate_reasoning_progress(registry, selection, progress)
    eligible = decision.terminal and decision.policy_compliant
    return ReasoningPolicyReceipt(
        registry_digest=registry.digest,
        selection_digest=selection.digest,
        progress_digest=progress.digest,
        decision_digest=decision.digest,
        strategy_id=selection.strategy_id,
        action=decision.action.value,
        terminal=decision.terminal,
        policy_compliant=decision.policy_compliant,
        eligible_for_promotion=eligible,
    )


__all__ = [
    "CognitiveRuntimeError",
    "ReasoningPolicyReceipt",
    "ReasoningProgress",
    "StopAction",
    "StopDecision",
    "build_reasoning_policy_receipt",
    "evaluate_reasoning_progress",
]
