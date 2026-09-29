"""Agent policy engine — how agents decide what to do.

An agent without a policy is just a sensor. This module gives agents
structured decision-making: rule-based heuristics, utility maximisation,
and a lightweight planner that picks the highest-value action given
beliefs about the world.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from skeleton.kernel.errors import AgentError


class PolicyError(AgentError):
    code = "AGT.POLICY"


@dataclass(frozen=True)
class Action:
    name: str
    cost: float = 0.0
    preconditions: Tuple[str, ...] = ()
    effects: Dict[str, Any] = field(default_factory=dict)

    def executable(self, state: Dict[str, Any]) -> bool:
        return all(p in state and state[p] for p in self.preconditions)


@dataclass
class BeliefState:
    """Agent's working model of the world."""

    facts: Dict[str, Any] = field(default_factory=dict)
    confidence: Dict[str, float] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.facts.get(key, default)

    def certainty(self, key: str) -> float:
        return self.confidence.get(key, 0.0)


class PolicyEngine:
    """Action selector: scores candidates and picks the best."""

    def __init__(
        self,
        *,
        scorer: Optional[Callable[[Action, BeliefState], float]] = None,
    ) -> None:
        self._scorer = scorer or self._default_score
        self._actions: Dict[str, Action] = {}

    def register(self, action: Action) -> None:
        self._actions[action.name] = action

    def decide(self, state: BeliefState) -> Optional[Action]:
        candidates = [
            (a, self._scorer(a, state))
            for a in self._actions.values()
            if a.executable(state.facts)
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda kv: -kv[1])
        return candidates[0][0]

    def options(self, state: BeliefState) -> Tuple[Tuple[Action, float], ...]:
        """All executable actions ranked by score."""
        ranked = sorted(
            ((a, self._scorer(a, state)) for a in self._actions.values() if a.executable(state.facts)),
            key=lambda kv: -kv[1],
        )
        return tuple(ranked)

    @staticmethod
    def _default_score(action: Action, state: BeliefState) -> float:
        """Higher is better: reward effect confidence minus cost."""
        effect_value = sum(
            state.certainty(k) * (1.0 if v else 0.0)
            for k, v in action.effects.items()
        )
        return effect_value - action.cost


class RulePolicy:
    """If-then rule engine for fast reactive decisions."""

    def __init__(self) -> None:
        self._rules: List[Tuple[Callable[[BeliefState], bool], Action]] = []

    def add_rule(
        self, condition: Callable[[BeliefState], bool], action: Action
    ) -> None:
        self._rules.append((condition, action))

    def decide(self, state: BeliefState) -> Optional[Action]:
        for condition, action in self._rules:
            if condition(state) and action.executable(state.facts):
                return action
        return None
