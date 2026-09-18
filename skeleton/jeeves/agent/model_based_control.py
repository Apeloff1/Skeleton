"""Model-based control and imagination for Jeeves.

This module provides an explicit learned transition model between compact agent
states and temporally abstract actions (options/skills).  It supports:

* Bayesian-ish transition/outcome counts with uncertainty estimates;
* reward/cost/latency running statistics;
* Dyna-style replay from real transitions into simulated planning updates;
* UCT/MCTS over option-level actions;
* particle-belief root states for partial observability;
* risk-aware rollout scoring and uncertainty penalties;
* model-error tracking so imagination loses authority when reality diverges;
* deterministic snapshots/fingerprints for replay and evaluation.

It does not execute tools and it never treats imagined transitions as evidence.
Simulation is advisory planning data only.  Real observations remain the source
of truth.
"""

from __future__ import annotations

import math
import random
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

from .types import (
    AgentContractError,
    RiskTier,
    bounded_text,
    finite_number,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)


class ModelControlError(RuntimeError):
    pass


class TransitionOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    BLOCKED = "blocked"
    INTERRUPTED = "interrupted"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CompactState:
    state_id: str
    features: Mapping[str, str]
    progress_bucket: int = 0
    uncertainty_bucket: int = 0
    budget_bucket: int = 0
    failure_bucket: int = 0
    risk: RiskTier = RiskTier.READ_ONLY
    terminal: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_id", require_id("state_id", self.state_id))
        normalized = {require_id("feature", str(key)): bounded_text("feature value", str(value), maximum=256, allow_empty=True) for key, value in dict(self.features).items()}
        object.__setattr__(self, "features", dict(sorted(normalized.items())))
        for name in ("progress_bucket", "uncertainty_bucket", "budget_bucket", "failure_bucket"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10:
                raise AgentContractError(f"{name} must be integer in [0, 10]")
        if not isinstance(self.risk, RiskTier):
            object.__setattr__(self, "risk", RiskTier(str(self.risk)))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "features": self.features,
                "progress": self.progress_bucket,
                "uncertainty": self.uncertainty_bucket,
                "budget": self.budget_bucket,
                "failure": self.failure_bucket,
                "risk": self.risk.value,
                "terminal": self.terminal,
            }
        )

    @classmethod
    def from_signals(
        cls,
        *,
        features: Mapping[str, Any],
        progress: float,
        uncertainty: float,
        budget_pressure: float,
        failure_pressure: float,
        risk: RiskTier,
        terminal: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> "CompactState":
        normalized_features = {str(key): str(value) for key, value in features.items()}
        payload = {
            "features": normalized_features,
            "progress": round(probability("progress", progress), 1),
            "uncertainty": round(probability("uncertainty", uncertainty), 1),
            "budget": round(probability("budget_pressure", budget_pressure), 1),
            "failure": round(probability("failure_pressure", failure_pressure), 1),
            "risk": risk.value,
            "terminal": terminal,
        }
        return cls(
            state_id=stable_id("mstate", payload),
            features=normalized_features,
            progress_bucket=min(10, round(progress * 10)),
            uncertainty_bucket=min(10, round(uncertainty * 10)),
            budget_bucket=min(10, round(budget_pressure * 10)),
            failure_bucket=min(10, round(failure_pressure * 10)),
            risk=risk,
            terminal=terminal,
            metadata=metadata or {},
        )


@dataclass(frozen=True, slots=True)
class AbstractAction:
    action_id: str
    name: str
    capability: str
    risk: RiskTier = RiskTier.READ_ONLY
    option_id: str | None = None
    estimated_external_cost: float = 0.0
    reversible: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_id", require_id("action_id", self.action_id))
        object.__setattr__(self, "name", bounded_text("name", self.name, maximum=1024))
        object.__setattr__(self, "capability", require_id("capability", self.capability))
        if not isinstance(self.risk, RiskTier):
            object.__setattr__(self, "risk", RiskTier(str(self.risk)))
        if self.option_id is not None:
            object.__setattr__(self, "option_id", require_id("option_id", self.option_id))
        cost = finite_number("estimated_external_cost", self.estimated_external_cost)
        if cost < 0:
            raise AgentContractError("estimated_external_cost must be non-negative")
        object.__setattr__(self, "estimated_external_cost", cost)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class TransitionExperience:
    experience_id: str
    run_id: str
    state: CompactState
    action: AbstractAction
    next_state: CompactState
    outcome: TransitionOutcome
    reward: float
    verification_score: float
    cost: float
    latency_ms: float
    observed_at: float
    evidence_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "experience_id", require_id("experience_id", self.experience_id))
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        if not isinstance(self.state, CompactState) or not isinstance(self.next_state, CompactState):
            raise AgentContractError("state/next_state must be CompactState")
        if not isinstance(self.action, AbstractAction):
            raise AgentContractError("action must be AbstractAction")
        if not isinstance(self.outcome, TransitionOutcome):
            object.__setattr__(self, "outcome", TransitionOutcome(str(self.outcome)))
        reward = finite_number("reward", self.reward)
        object.__setattr__(self, "reward", max(-1.0, min(1.0, reward)))
        object.__setattr__(self, "verification_score", probability("verification_score", self.verification_score))
        for name in ("cost", "latency_ms"):
            value = finite_number(name, getattr(self, name))
            if value < 0:
                raise AgentContractError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        observed = finite_number("observed_at", self.observed_at)
        if observed < 0:
            raise AgentContractError("observed_at must be non-negative")
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "evidence_ids", tuple(require_id("evidence_id", item) for item in self.evidence_ids))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(slots=True)
class RunningMoments:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def update(self, value: float) -> None:
        value = finite_number("value", value)
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)

    @property
    def variance(self) -> float:
        return self.m2 / (self.count - 1) if self.count > 1 else 0.0

    @property
    def stddev(self) -> float:
        return math.sqrt(max(0.0, self.variance))


@dataclass(slots=True)
class TransitionCell:
    state_id: str
    action_id: str
    next_counts: Counter[str] = field(default_factory=Counter)
    outcome_counts: Counter[TransitionOutcome] = field(default_factory=Counter)
    reward: RunningMoments = field(default_factory=RunningMoments)
    verification: RunningMoments = field(default_factory=RunningMoments)
    cost: RunningMoments = field(default_factory=RunningMoments)
    latency: RunningMoments = field(default_factory=RunningMoments)
    observations: int = 0
    last_observed_at: float = 0.0
    model_error: RunningMoments = field(default_factory=RunningMoments)

    @property
    def uncertainty(self) -> float:
        if self.observations == 0:
            return 1.0
        count_uncertainty = 1.0 / math.sqrt(self.observations)
        transition_entropy = 0.0
        total = sum(self.next_counts.values())
        if total:
            for count in self.next_counts.values():
                p = count / total
                transition_entropy -= p * math.log2(p)
            max_entropy = math.log2(max(2, len(self.next_counts)))
            transition_entropy = transition_entropy / max_entropy if max_entropy else 0.0
        error_penalty = min(1.0, self.model_error.mean if self.model_error.count else 0.0)
        return max(0.0, min(1.0, count_uncertainty * 0.45 + transition_entropy * 0.35 + error_penalty * 0.20))


@dataclass(frozen=True, slots=True)
class PredictedTransition:
    state_id: str
    action_id: str
    next_state_probabilities: Mapping[str, float]
    outcome_probabilities: Mapping[str, float]
    expected_reward: float
    expected_verification: float
    expected_cost: float
    expected_latency_ms: float
    uncertainty: float
    observations: int


class LearnedTransitionModel:
    """Finite empirical model over abstract states/actions."""

    def __init__(self, *, max_experiences: int = 1_000_000) -> None:
        self.max_experiences = positive_int("max_experiences", max_experiences, maximum=20_000_000)
        self._states: dict[str, CompactState] = {}
        self._actions: dict[str, AbstractAction] = {}
        self._cells: dict[tuple[str, str], TransitionCell] = {}
        self._experiences: deque[TransitionExperience] = deque(maxlen=max_experiences)
        self._reverse: dict[str, set[tuple[str, str]]] = defaultdict(set)
        self._lock = threading.RLock()

    def observe(self, experience: TransitionExperience) -> None:
        if not isinstance(experience, TransitionExperience):
            raise TypeError("experience must be TransitionExperience")
        key = (experience.state.state_id, experience.action.action_id)
        with self._lock:
            self._states[experience.state.state_id] = experience.state
            self._states[experience.next_state.state_id] = experience.next_state
            self._actions[experience.action.action_id] = experience.action
            cell = self._cells.setdefault(key, TransitionCell(*key))
            cell.next_counts[experience.next_state.state_id] += 1
            cell.outcome_counts[experience.outcome] += 1
            cell.reward.update(experience.reward)
            cell.verification.update(experience.verification_score)
            cell.cost.update(experience.cost)
            cell.latency.update(experience.latency_ms)
            cell.observations += 1
            cell.last_observed_at = max(cell.last_observed_at, experience.observed_at)
            self._reverse[experience.next_state.state_id].add(key)
            self._experiences.append(experience)

    def record_prediction_error(self, state_id: str, action_id: str, *, predicted_next: str, actual_next: str) -> None:
        key = (require_id("state_id", state_id), require_id("action_id", action_id))
        with self._lock:
            cell = self._cells.get(key)
            if cell is None:
                return
            predicted_probability = self.predict(state_id, action_id).next_state_probabilities.get(actual_next, 0.0)
            error = 1.0 - predicted_probability
            if predicted_next == actual_next:
                error *= 0.5
            cell.model_error.update(error)

    def predict(self, state_id: str, action_id: str, *, prior: float = 0.5) -> PredictedTransition:
        state_id = require_id("state_id", state_id)
        action_id = require_id("action_id", action_id)
        key = (state_id, action_id)
        with self._lock:
            cell = self._cells.get(key)
            if cell is None:
                return PredictedTransition(state_id, action_id, {}, {}, 0.0, prior, 0.0, 0.0, 1.0, 0)
            next_total = sum(cell.next_counts.values())
            outcome_total = sum(cell.outcome_counts.values())
            next_probs = {sid: count / next_total for sid, count in sorted(cell.next_counts.items())} if next_total else {}
            outcome_probs = {outcome.value: count / outcome_total for outcome, count in sorted(cell.outcome_counts.items(), key=lambda item: item[0].value)} if outcome_total else {}
            return PredictedTransition(
                state_id=state_id,
                action_id=action_id,
                next_state_probabilities=next_probs,
                outcome_probabilities=outcome_probs,
                expected_reward=cell.reward.mean,
                expected_verification=cell.verification.mean if cell.verification.count else prior,
                expected_cost=cell.cost.mean,
                expected_latency_ms=cell.latency.mean,
                uncertainty=cell.uncertainty,
                observations=cell.observations,
            )

    def actions_from(self, state_id: str) -> tuple[AbstractAction, ...]:
        state_id = require_id("state_id", state_id)
        with self._lock:
            ids = sorted(action_id for s_id, action_id in self._cells if s_id == state_id)
            return tuple(self._actions[action_id] for action_id in ids)

    def state(self, state_id: str) -> CompactState | None:
        with self._lock:
            return self._states.get(require_id("state_id", state_id))

    def action(self, action_id: str) -> AbstractAction | None:
        with self._lock:
            return self._actions.get(require_id("action_id", action_id))

    def predecessors(self, state_id: str) -> tuple[tuple[CompactState, AbstractAction], ...]:
        state_id = require_id("state_id", state_id)
        with self._lock:
            keys = sorted(self._reverse.get(state_id, ()))
            return tuple((self._states[sid], self._actions[aid]) for sid, aid in keys)

    def recent(self, *, limit: int = 1000) -> tuple[TransitionExperience, ...]:
        limit = positive_int("limit", limit, maximum=self.max_experiences)
        with self._lock:
            return tuple(list(self._experiences)[-limit:])

    @property
    def fingerprint(self) -> str:
        with self._lock:
            payload = []
            for key in sorted(self._cells):
                cell = self._cells[key]
                payload.append(
                    {
                        "key": key,
                        "next": sorted(cell.next_counts.items()),
                        "outcomes": sorted((outcome.value, count) for outcome, count in cell.outcome_counts.items()),
                        "reward": (cell.reward.count, cell.reward.mean, cell.reward.m2),
                        "verification": (cell.verification.count, cell.verification.mean, cell.verification.m2),
                        "error": (cell.model_error.count, cell.model_error.mean, cell.model_error.m2),
                    }
                )
            return stable_fingerprint(payload)


@dataclass(slots=True)
class ValueEstimate:
    value: float = 0.0
    visits: int = 0


class DynaValueModel:
    """Tabular action-value estimates updated from real and simulated steps."""

    def __init__(self, *, alpha: float = 0.15, gamma: float = 0.95) -> None:
        self.alpha = probability("alpha", alpha)
        self.gamma = probability("gamma", gamma)
        self._q: dict[tuple[str, str], ValueEstimate] = {}
        self._lock = threading.RLock()

    def value(self, state_id: str, action_id: str) -> float:
        with self._lock:
            return self._q.get((state_id, action_id), ValueEstimate()).value

    def best_value(self, state_id: str, actions: Sequence[AbstractAction]) -> float:
        if not actions:
            return 0.0
        return max(self.value(state_id, action.action_id) for action in actions)

    def update(
        self,
        *,
        state_id: str,
        action_id: str,
        reward: float,
        next_state_id: str,
        next_actions: Sequence[AbstractAction],
        terminal: bool,
        weight: float = 1.0,
    ) -> float:
        reward = max(-1.0, min(1.0, finite_number("reward", reward)))
        weight = probability("weight", weight)
        target = reward if terminal else reward + self.gamma * self.best_value(next_state_id, next_actions)
        key = (require_id("state_id", state_id), require_id("action_id", action_id))
        with self._lock:
            estimate = self._q.setdefault(key, ValueEstimate())
            effective_alpha = self.alpha * max(0.05, weight)
            estimate.value += effective_alpha * (target - estimate.value)
            estimate.visits += 1
            return estimate.value

    def policy(self, state_id: str, actions: Sequence[AbstractAction]) -> tuple[tuple[AbstractAction, float], ...]:
        values = [(action, self.value(state_id, action.action_id)) for action in actions]
        values.sort(key=lambda item: (item[1], item[0].action_id), reverse=True)
        return tuple(values)

    @property
    def fingerprint(self) -> str:
        with self._lock:
            return stable_fingerprint([(key, estimate.value, estimate.visits) for key, estimate in sorted(self._q.items())])


@dataclass(frozen=True, slots=True)
class DynaConfig:
    planning_updates_per_real_step: int = 16
    replay_recent_fraction: float = 0.6
    minimum_model_confidence: float = 0.25
    model_uncertainty_penalty: float = 0.35
    verification_weight: float = 0.30
    cost_weight: float = 0.10

    def __post_init__(self) -> None:
        object.__setattr__(self, "planning_updates_per_real_step", positive_int("planning_updates_per_real_step", self.planning_updates_per_real_step, maximum=100_000))
        for name in ("replay_recent_fraction", "minimum_model_confidence", "model_uncertainty_penalty", "verification_weight", "cost_weight"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))


class DynaPlanner:
    def __init__(
        self,
        transition_model: LearnedTransitionModel,
        *,
        values: DynaValueModel | None = None,
        config: DynaConfig | None = None,
        seed: int = 0,
    ) -> None:
        self.model = transition_model
        self.values = values or DynaValueModel()
        self.config = config or DynaConfig()
        self._rng = random.Random(seed)
        self._lock = threading.RLock()

    def learn_real(self, experience: TransitionExperience) -> None:
        self.model.observe(experience)
        next_actions = self.model.actions_from(experience.next_state.state_id)
        weight = experience.verification_score
        self.values.update(
            state_id=experience.state.state_id,
            action_id=experience.action.action_id,
            reward=self._shaped_reward(experience),
            next_state_id=experience.next_state.state_id,
            next_actions=next_actions,
            terminal=experience.next_state.terminal,
            weight=weight,
        )
        self.plan(self.config.planning_updates_per_real_step)

    def plan(self, updates: int) -> int:
        updates = positive_int("updates", updates, maximum=1_000_000)
        experiences = self.model.recent(limit=min(20_000, max(100, updates * 20)))
        if not experiences:
            return 0
        completed = 0
        for _ in range(updates):
            if self._rng.random() < self.config.replay_recent_fraction:
                pool = experiences[max(0, len(experiences) - max(1, len(experiences) // 3)) :]
            else:
                pool = experiences
            seed_exp = self._rng.choice(pool)
            prediction = self.model.predict(seed_exp.state.state_id, seed_exp.action.action_id)
            if prediction.observations == 0 or 1.0 - prediction.uncertainty < self.config.minimum_model_confidence:
                continue
            next_state_id = self._sample_distribution(prediction.next_state_probabilities)
            if next_state_id is None:
                continue
            next_state = self.model.state(next_state_id)
            if next_state is None:
                continue
            uncertainty_weight = max(0.05, 1.0 - prediction.uncertainty * self.config.model_uncertainty_penalty)
            reward = prediction.expected_reward
            reward += self.config.verification_weight * (prediction.expected_verification - 0.5)
            reward -= self.config.cost_weight * min(1.0, prediction.expected_cost)
            self.values.update(
                state_id=seed_exp.state.state_id,
                action_id=seed_exp.action.action_id,
                reward=reward,
                next_state_id=next_state_id,
                next_actions=self.model.actions_from(next_state_id),
                terminal=next_state.terminal,
                weight=uncertainty_weight,
            )
            completed += 1
        return completed

    def _sample_distribution(self, distribution: Mapping[str, float]) -> str | None:
        if not distribution:
            return None
        threshold = self._rng.random()
        cumulative = 0.0
        last: str | None = None
        for key, p in sorted(distribution.items()):
            cumulative += p
            last = key
            if threshold <= cumulative:
                return key
        return last

    def _shaped_reward(self, experience: TransitionExperience) -> float:
        reward = experience.reward
        reward += self.config.verification_weight * (experience.verification_score - 0.5)
        reward -= self.config.cost_weight * min(1.0, experience.cost)
        if experience.outcome is TransitionOutcome.SUCCESS:
            reward += 0.10
        elif experience.outcome in {TransitionOutcome.FAILURE, TransitionOutcome.BLOCKED}:
            reward -= 0.15
        return max(-1.0, min(1.0, reward))


@dataclass(frozen=True, slots=True)
class SearchConfig:
    simulations: int = 256
    max_depth: int = 8
    exploration_constant: float = math.sqrt(2.0)
    discount: float = 0.95
    uncertainty_penalty: float = 0.20
    risk_penalty: float = 0.15
    cost_penalty: float = 0.05
    verification_bonus: float = 0.10
    minimum_observations_for_model: int = 1
    rollout_epsilon: float = 0.10

    def __post_init__(self) -> None:
        object.__setattr__(self, "simulations", positive_int("simulations", self.simulations, maximum=1_000_000))
        object.__setattr__(self, "max_depth", positive_int("max_depth", self.max_depth, maximum=10_000))
        exploration = finite_number("exploration_constant", self.exploration_constant)
        if exploration < 0:
            raise AgentContractError("exploration_constant must be non-negative")
        object.__setattr__(self, "exploration_constant", exploration)
        object.__setattr__(self, "discount", probability("discount", self.discount))
        for name in ("uncertainty_penalty", "risk_penalty", "cost_penalty", "verification_bonus", "rollout_epsilon"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        object.__setattr__(self, "minimum_observations_for_model", positive_int("minimum_observations_for_model", self.minimum_observations_for_model, maximum=1_000_000))


@dataclass(slots=True)
class TreeNode:
    state_id: str
    parent: "TreeNode | None" = None
    action_from_parent: str | None = None
    visits: int = 0
    value_sum: float = 0.0
    children: dict[str, "TreeNode"] = field(default_factory=dict)
    unexpanded_actions: list[str] = field(default_factory=list)
    terminal: bool = False
    depth: int = 0

    @property
    def mean_value(self) -> float:
        return self.value_sum / self.visits if self.visits else 0.0


@dataclass(frozen=True, slots=True)
class SearchActionValue:
    action: AbstractAction
    visits: int
    mean_value: float
    confidence: float
    model_uncertainty: float
    expected_reward: float
    expected_verification: float
    expected_cost: float


@dataclass(frozen=True, slots=True)
class ModelSearchResult:
    root_state_id: str
    selected_action: AbstractAction | None
    action_values: tuple[SearchActionValue, ...]
    simulations: int
    expanded_nodes: int
    maximum_depth_reached: int
    model_fingerprint: str
    value_fingerprint: str
    trace_fingerprint: str


class OptionMCTS:
    _RISK = {
        RiskTier.READ_ONLY: 0.0,
        RiskTier.REVERSIBLE: 0.15,
        RiskTier.MUTATING: 0.40,
        RiskTier.EXTERNAL: 0.70,
        RiskTier.HIGH_IMPACT: 1.0,
    }

    def __init__(
        self,
        model: LearnedTransitionModel,
        *,
        dyna_values: DynaValueModel | None = None,
        config: SearchConfig | None = None,
        seed: int = 0,
    ) -> None:
        self.model = model
        self.values = dyna_values or DynaValueModel()
        self.config = config or SearchConfig()
        self._rng = random.Random(seed)

    def search(
        self,
        root_state_id: str,
        *,
        allowed_action_ids: Sequence[str] | None = None,
        maximum_risk: RiskTier = RiskTier.HIGH_IMPACT,
    ) -> ModelSearchResult:
        root_state_id = require_id("root_state_id", root_state_id)
        root_state = self.model.state(root_state_id)
        if root_state is None:
            raise ModelControlError(f"unknown root state: {root_state_id}")
        allowed = None if allowed_action_ids is None else {require_id("allowed_action_id", item) for item in allowed_action_ids}
        risk_order = {
            RiskTier.READ_ONLY: 0,
            RiskTier.REVERSIBLE: 1,
            RiskTier.MUTATING: 2,
            RiskTier.EXTERNAL: 3,
            RiskTier.HIGH_IMPACT: 4,
        }
        root_actions = [
            action
            for action in self.model.actions_from(root_state_id)
            if (allowed is None or action.action_id in allowed) and risk_order[action.risk] <= risk_order[maximum_risk]
        ]
        root = TreeNode(root_state_id, terminal=root_state.terminal, unexpanded_actions=[action.action_id for action in root_actions])
        expanded_nodes = 1
        max_depth = 0
        for _ in range(self.config.simulations):
            node = root
            path = [node]
            rewards: list[float] = []
            while not node.terminal and node.depth < self.config.max_depth:
                max_depth = max(max_depth, node.depth)
                if node.unexpanded_actions:
                    action_id = node.unexpanded_actions.pop(0)
                    transition = self.model.predict(node.state_id, action_id)
                    next_state_id = self._sample_next(transition)
                    if next_state_id is None:
                        break
                    next_state = self.model.state(next_state_id)
                    if next_state is None:
                        break
                    reward = self._transition_value(action_id, transition)
                    child_actions = [action.action_id for action in self.model.actions_from(next_state_id)]
                    child = TreeNode(
                        state_id=next_state_id,
                        parent=node,
                        action_from_parent=action_id,
                        terminal=next_state.terminal,
                        unexpanded_actions=child_actions,
                        depth=node.depth + 1,
                    )
                    node.children[action_id] = child
                    node = child
                    path.append(node)
                    rewards.append(reward)
                    expanded_nodes += 1
                    break
                if not node.children:
                    break
                action_id, child = self._select_uct(node)
                transition = self.model.predict(node.state_id, action_id)
                rewards.append(self._transition_value(action_id, transition))
                node = child
                path.append(node)
            rollout = self._rollout(node.state_id, node.depth)
            returns = self._backward_returns(rewards, rollout)
            for index, path_node in enumerate(path):
                path_node.visits += 1
                value = returns[index] if index < len(returns) else rollout
                path_node.value_sum += value
        action_values: list[SearchActionValue] = []
        for action_id, child in root.children.items():
            action = self.model.action(action_id)
            if action is None:
                continue
            prediction = self.model.predict(root_state_id, action_id)
            confidence = 1.0 - prediction.uncertainty
            action_values.append(
                SearchActionValue(
                    action=action,
                    visits=child.visits,
                    mean_value=child.mean_value,
                    confidence=confidence,
                    model_uncertainty=prediction.uncertainty,
                    expected_reward=prediction.expected_reward,
                    expected_verification=prediction.expected_verification,
                    expected_cost=prediction.expected_cost,
                )
            )
        action_values.sort(key=lambda item: (item.visits, item.mean_value, item.confidence, item.action.action_id), reverse=True)
        selected = action_values[0].action if action_values else None
        trace = stable_fingerprint(
            {
                "root": root_state_id,
                "selected": selected.action_id if selected else None,
                "values": [
                    (
                        item.action.action_id,
                        item.visits,
                        item.mean_value,
                        item.confidence,
                        item.model_uncertainty,
                    )
                    for item in action_values
                ],
                "simulations": self.config.simulations,
                "model": self.model.fingerprint,
                "values_fp": self.values.fingerprint,
            }
        )
        return ModelSearchResult(
            root_state_id=root_state_id,
            selected_action=selected,
            action_values=tuple(action_values),
            simulations=self.config.simulations,
            expanded_nodes=expanded_nodes,
            maximum_depth_reached=max_depth,
            model_fingerprint=self.model.fingerprint,
            value_fingerprint=self.values.fingerprint,
            trace_fingerprint=trace,
        )

    def _select_uct(self, node: TreeNode) -> tuple[str, TreeNode]:
        best: tuple[float, str, TreeNode] | None = None
        parent_visits = max(1, node.visits)
        for action_id, child in node.children.items():
            exploitation = child.mean_value
            exploration = self.config.exploration_constant * math.sqrt(math.log(parent_visits + 1) / max(1, child.visits))
            transition = self.model.predict(node.state_id, action_id)
            uncertainty_penalty = transition.uncertainty * self.config.uncertainty_penalty
            score = exploitation + exploration - uncertainty_penalty
            candidate = (score, action_id, child)
            if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and action_id < best[1]):
                best = candidate
        if best is None:
            raise ModelControlError("UCT selection on leaf")
        return best[1], best[2]

    def _sample_next(self, transition: PredictedTransition) -> str | None:
        if transition.observations < self.config.minimum_observations_for_model:
            return None
        distribution = transition.next_state_probabilities
        if not distribution:
            return None
        threshold = self._rng.random()
        cumulative = 0.0
        last: str | None = None
        for state_id, p in sorted(distribution.items()):
            cumulative += p
            last = state_id
            if threshold <= cumulative:
                return state_id
        return last

    def _transition_value(self, action_id: str, transition: PredictedTransition) -> float:
        action = self.model.action(action_id)
        if action is None:
            return -1.0
        value = transition.expected_reward
        value += self.config.verification_bonus * (transition.expected_verification - 0.5)
        value -= self.config.uncertainty_penalty * transition.uncertainty
        value -= self.config.risk_penalty * self._RISK[action.risk]
        value -= self.config.cost_penalty * min(1.0, transition.expected_cost)
        return max(-1.0, min(1.0, value))

    def _rollout(self, state_id: str, depth: int) -> float:
        total = 0.0
        discount = 1.0
        current = state_id
        for _ in range(depth, self.config.max_depth):
            state = self.model.state(current)
            if state is None or state.terminal:
                break
            actions = list(self.model.actions_from(current))
            if not actions:
                break
            if self._rng.random() < self.config.rollout_epsilon:
                action = self._rng.choice(actions)
            else:
                ranked = self.values.policy(current, actions)
                action = ranked[0][0] if ranked else actions[0]
            transition = self.model.predict(current, action.action_id)
            next_state = self._sample_next(transition)
            if next_state is None:
                break
            total += discount * self._transition_value(action.action_id, transition)
            discount *= self.config.discount
            current = next_state
        return total

    def _backward_returns(self, rewards: Sequence[float], rollout: float) -> list[float]:
        if not rewards:
            return [rollout]
        returns = [0.0] * (len(rewards) + 1)
        returns[-1] = rollout
        running = rollout
        for index in range(len(rewards) - 1, -1, -1):
            running = rewards[index] + self.config.discount * running
            returns[index] = running
        return returns


@dataclass(frozen=True, slots=True)
class BeliefRoot:
    particles: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        particles = tuple((require_id("state_id", state_id), probability("particle probability", p)) for state_id, p in self.particles)
        if not particles:
            raise AgentContractError("belief root requires particles")
        total = sum(p for _, p in particles)
        if total <= 0:
            raise AgentContractError("belief root probability mass is zero")
        normalized = tuple((state_id, p / total) for state_id, p in particles)
        object.__setattr__(self, "particles", normalized)


@dataclass(frozen=True, slots=True)
class BeliefSearchResult:
    selected_action: AbstractAction | None
    expected_action_values: tuple[tuple[AbstractAction, float, float], ...]
    particle_results: tuple[tuple[str, float, ModelSearchResult], ...]
    fingerprint: str


class BeliefMCTS:
    """Approximate root-belief search by aggregating particle MCTS results."""

    def __init__(self, searcher: OptionMCTS) -> None:
        self.searcher = searcher

    def search(
        self,
        belief: BeliefRoot,
        *,
        allowed_action_ids: Sequence[str] | None = None,
        maximum_risk: RiskTier = RiskTier.HIGH_IMPACT,
    ) -> BeliefSearchResult:
        if not isinstance(belief, BeliefRoot):
            raise TypeError("belief must be BeliefRoot")
        particle_results: list[tuple[str, float, ModelSearchResult]] = []
        aggregate: dict[str, list[float]] = defaultdict(list)
        weighted_sum: Counter[str] = Counter()
        weight_sum: Counter[str] = Counter()
        for state_id, particle_weight in belief.particles:
            result = self.searcher.search(state_id, allowed_action_ids=allowed_action_ids, maximum_risk=maximum_risk)
            particle_results.append((state_id, particle_weight, result))
            for value in result.action_values:
                weighted_sum[value.action.action_id] += particle_weight * value.mean_value
                weight_sum[value.action.action_id] += particle_weight
                aggregate[value.action.action_id].append(value.mean_value)
        rows: list[tuple[AbstractAction, float, float]] = []
        for action_id in sorted(weighted_sum):
            action = self.searcher.model.action(action_id)
            if action is None:
                continue
            expected = weighted_sum[action_id] / max(1e-9, weight_sum[action_id])
            vals = aggregate[action_id]
            variance = sum((value - expected) ** 2 for value in vals) / len(vals) if vals else 0.0
            rows.append((action, expected, math.sqrt(max(0.0, variance))))
        rows.sort(key=lambda item: (item[1] - 0.20 * item[2], item[0].action_id), reverse=True)
        selected = rows[0][0] if rows else None
        fingerprint = stable_fingerprint(
            {
                "belief": belief.particles,
                "selected": selected.action_id if selected else None,
                "rows": [(action.action_id, value, uncertainty) for action, value, uncertainty in rows],
                "particles": [(state_id, weight, result.trace_fingerprint) for state_id, weight, result in particle_results],
            }
        )
        return BeliefSearchResult(selected, tuple(rows), tuple(particle_results), fingerprint)


def transition_experience(
    *,
    run_id: str,
    state: CompactState,
    action: AbstractAction,
    next_state: CompactState,
    outcome: TransitionOutcome,
    reward: float,
    verification_score: float,
    cost: float = 0.0,
    latency_ms: float = 0.0,
    observed_at: float | None = None,
    evidence_ids: Sequence[str] = (),
    metadata: Mapping[str, Any] | None = None,
) -> TransitionExperience:
    at = time.time() if observed_at is None else observed_at
    payload = {
        "run": run_id,
        "state": state.state_id,
        "action": action.action_id,
        "next": next_state.state_id,
        "outcome": outcome.value,
        "reward": reward,
        "verification": verification_score,
        "at": at,
        "evidence": tuple(evidence_ids),
    }
    return TransitionExperience(
        experience_id=stable_id("transition", payload),
        run_id=run_id,
        state=state,
        action=action,
        next_state=next_state,
        outcome=outcome,
        reward=reward,
        verification_score=verification_score,
        cost=cost,
        latency_ms=latency_ms,
        observed_at=at,
        evidence_ids=tuple(evidence_ids),
        metadata=metadata or {},
    )
