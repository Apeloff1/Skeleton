"""Typed world-model rollout and simulation authority boundary for VOL-019.

The low-level deterministic environment adapter remains the execution substrate.
This module standardizes environment adapters, assumptions, uncertainty
propagation, rollout receipts, and counterfactual comparison while preserving a
hard rule: simulated success is never real-world postcondition evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Mapping, Protocol, Sequence, runtime_checkable

from skeleton.contracts.canonical import CanonicalContractError, canonical_json_bytes
from skeleton.simulation.environment import (
    EnvironmentTransition,
    SimulationBoundaryError,
)
from skeleton.simulation.world import WorldState


WORLD_MODEL_SCHEMA = "skeleton.world_model_simulation.v1"


class WorldModelError(SimulationBoundaryError):
    """World-model contract or adapter evidence is invalid."""


def _token(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str):
        raise WorldModelError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized or normalized != value or len(normalized) > maximum:
        raise WorldModelError(f"{field} must be a canonical non-empty token")
    return normalized


def _sha256(value: object, field: str) -> str:
    token = _token(value, field, maximum=64)
    if len(token) != 64 or any(ch not in "0123456789abcdef" for ch in token):
        raise WorldModelError(f"{field} must be a lowercase SHA-256 digest")
    return token


def _unit(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorldModelError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise WorldModelError(f"{field} must be within [0, 1]")
    return result


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorldModelError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise WorldModelError(f"{field} must be finite numeric")
    return result


def _canonical_json(value: object, field: str) -> bytes:
    try:
        return canonical_json_bytes(value)
    except CanonicalContractError as exc:
        raise WorldModelError(f"{field} must be deterministic JSON") from exc


def _digest(value: object, field: str = "payload") -> str:
    return hashlib.sha256(_canonical_json(value, field)).hexdigest()


def _mapping_digest(value: Mapping[str, object], field: str) -> str:
    if not isinstance(value, Mapping):
        raise WorldModelError(f"{field} must be a mapping")
    return _digest(dict(value), field)


@dataclass(frozen=True, slots=True)
class Assumption:
    """One explicit model assumption and its epistemic uncertainty."""

    assumption_id: str
    statement: str
    uncertainty: float
    source_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "assumption_id",
            _token(self.assumption_id, "assumption_id", maximum=128),
        )
        object.__setattr__(
            self,
            "statement",
            _token(self.statement, "statement", maximum=2048),
        )
        object.__setattr__(
            self,
            "uncertainty",
            _unit(self.uncertainty, "uncertainty"),
        )
        object.__setattr__(
            self,
            "source_ref",
            _token(self.source_ref, "source_ref", maximum=1024),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": WORLD_MODEL_SCHEMA,
                "kind": "assumption",
                "assumption_id": self.assumption_id,
                "statement": self.statement,
                "uncertainty": self.uncertainty,
                "source_ref": self.source_ref,
            }
        )


@dataclass(frozen=True, slots=True)
class AssumptionSet:
    """Canonical, deduplicated assumptions for one simulated rollout."""

    assumptions: tuple[Assumption, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.assumptions, tuple):
            raise WorldModelError("assumptions must be a tuple")
        by_id: dict[str, Assumption] = {}
        for item in self.assumptions:
            if not isinstance(item, Assumption):
                raise WorldModelError(
                    "assumptions must contain Assumption values"
                )
            if item.assumption_id in by_id:
                raise WorldModelError("duplicate assumption_id")
            by_id[item.assumption_id] = item
        canonical = tuple(by_id[key] for key in sorted(by_id))
        object.__setattr__(self, "assumptions", canonical)

    @property
    def aggregate_uncertainty(self) -> float:
        """Conservative union: any uncertain assumption can invalidate rollout."""

        survival = 1.0
        for item in self.assumptions:
            survival *= 1.0 - item.uncertainty
        return 1.0 - survival

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": WORLD_MODEL_SCHEMA,
                "kind": "assumption-set",
                "assumptions": [
                    {
                        "assumption_id": item.assumption_id,
                        "digest": item.digest,
                    }
                    for item in self.assumptions
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class UncertaintyPropagationPolicy:
    """Monotonic conservative-union uncertainty propagation.

    The policy never lets later steps reduce uncertainty accumulated from
    assumptions or earlier transitions.
    """

    policy_id: str = "conservative-union-v1"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_id",
            _token(self.policy_id, "policy_id", maximum=128),
        )

    def combine(self, prior: float, observed: float) -> float:
        left = _unit(prior, "prior_uncertainty")
        right = _unit(observed, "observed_uncertainty")
        combined = 1.0 - ((1.0 - left) * (1.0 - right))
        if combined + 1e-15 < left or combined + 1e-15 < right:
            raise WorldModelError("uncertainty propagation must be monotonic")
        return min(1.0, max(0.0, combined))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": WORLD_MODEL_SCHEMA,
                "kind": "uncertainty-policy",
                "policy_id": self.policy_id,
            }
        )


@runtime_checkable
class EnvironmentAdapter(Protocol):
    """Minimal environment contract required by the rollout engine."""

    simulation_id: str
    seed: int

    @property
    def state(self) -> Mapping[str, object]:
        ...

    def reset(self) -> Mapping[str, object]:
        ...

    def step(self, action: Mapping[str, object]) -> EnvironmentTransition:
        ...


@dataclass(frozen=True, slots=True)
class SimulationStep:
    step_index: int
    action_digest: str
    prior_state_digest: str
    next_state_digest: str
    reward: float
    terminal: bool
    local_uncertainty: float
    cumulative_uncertainty: float
    evidence_digest: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.step_index, bool)
            or not isinstance(self.step_index, int)
            or self.step_index < 0
        ):
            raise WorldModelError("step_index must be non-negative")
        for field in (
            "action_digest",
            "prior_state_digest",
            "next_state_digest",
            "evidence_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(self, "reward", _finite(self.reward, "reward"))
        if not isinstance(self.terminal, bool):
            raise WorldModelError("terminal must be boolean")
        local = _unit(self.local_uncertainty, "local_uncertainty")
        cumulative = _unit(
            self.cumulative_uncertainty,
            "cumulative_uncertainty",
        )
        if cumulative + 1e-15 < local:
            raise WorldModelError(
                "cumulative uncertainty cannot be below local uncertainty"
            )
        object.__setattr__(self, "local_uncertainty", local)
        object.__setattr__(self, "cumulative_uncertainty", cumulative)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": WORLD_MODEL_SCHEMA,
                "kind": "simulation-step",
                "step_index": self.step_index,
                "action_digest": self.action_digest,
                "prior_state_digest": self.prior_state_digest,
                "next_state_digest": self.next_state_digest,
                "reward": self.reward,
                "terminal": self.terminal,
                "local_uncertainty": self.local_uncertainty,
                "cumulative_uncertainty": self.cumulative_uncertainty,
                "evidence_digest": self.evidence_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class SimulationResult:
    simulation_id: str
    seed: int
    assumption_set_digest: str
    uncertainty_policy_digest: str
    initial_state_digest: str
    final_state_digest: str
    steps: tuple[SimulationStep, ...]
    cumulative_uncertainty: float
    terminal: bool
    evidence_class: str = "simulation"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "simulation_id",
            _token(self.simulation_id, "simulation_id"),
        )
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise WorldModelError("seed must be an integer")
        for field in (
            "assumption_set_digest",
            "uncertainty_policy_digest",
            "initial_state_digest",
            "final_state_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if not isinstance(self.steps, tuple):
            raise WorldModelError("steps must be a tuple")
        previous = -1.0
        expected_index = 0
        for step in self.steps:
            if not isinstance(step, SimulationStep):
                raise WorldModelError("steps must contain SimulationStep")
            if step.step_index != expected_index:
                raise WorldModelError("simulation step indices must be contiguous")
            if step.cumulative_uncertainty + 1e-15 < previous:
                raise WorldModelError(
                    "simulation uncertainty cannot decrease across rollout"
                )
            previous = step.cumulative_uncertainty
            expected_index += 1
        cumulative = _unit(
            self.cumulative_uncertainty,
            "cumulative_uncertainty",
        )
        if self.steps and abs(
            self.steps[-1].cumulative_uncertainty - cumulative
        ) > 1e-12:
            raise WorldModelError(
                "result uncertainty must equal final step uncertainty"
            )
        if not isinstance(self.terminal, bool):
            raise WorldModelError("terminal must be boolean")
        if self.steps and self.steps[-1].terminal != self.terminal:
            raise WorldModelError("terminal state does not match final step")
        if self.evidence_class != "simulation":
            raise WorldModelError(
                "world-model results must remain simulation evidence"
            )
        object.__setattr__(self, "cumulative_uncertainty", cumulative)

    @property
    def can_support_real_world_fact(self) -> bool:
        return False

    @property
    def can_satisfy_real_postcondition(self) -> bool:
        return False

    def require_real_world_postcondition_authority(self) -> None:
        raise WorldModelError(
            "simulation result cannot satisfy a real-world postcondition"
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": WORLD_MODEL_SCHEMA,
                "kind": "simulation-result",
                "simulation_id": self.simulation_id,
                "seed": self.seed,
                "assumption_set_digest": self.assumption_set_digest,
                "uncertainty_policy_digest": self.uncertainty_policy_digest,
                "initial_state_digest": self.initial_state_digest,
                "final_state_digest": self.final_state_digest,
                "steps": [step.digest for step in self.steps],
                "cumulative_uncertainty": self.cumulative_uncertainty,
                "terminal": self.terminal,
                "evidence_class": self.evidence_class,
            }
        )


@dataclass(frozen=True, slots=True)
class CounterfactualResult:
    case_id: str
    result: SimulationResult

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "case_id",
            _token(self.case_id, "case_id", maximum=128),
        )
        if not isinstance(self.result, SimulationResult):
            raise WorldModelError("result must be SimulationResult")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": WORLD_MODEL_SCHEMA,
                "kind": "counterfactual-result",
                "case_id": self.case_id,
                "result_digest": self.result.digest,
            }
        )


class CounterfactualRolloutEngine:
    """Verify and aggregate deterministic simulation rollouts."""

    def __init__(
        self,
        adapter: EnvironmentAdapter,
        *,
        assumptions: AssumptionSet | None = None,
        uncertainty_policy: UncertaintyPropagationPolicy | None = None,
        max_steps: int = 1024,
        max_cases: int = 64,
    ) -> None:
        for attr in ("simulation_id", "seed", "state", "reset", "step"):
            if not hasattr(adapter, attr):
                raise WorldModelError(
                    f"environment adapter is missing {attr}"
                )
        simulation_id = _token(
            getattr(adapter, "simulation_id"),
            "simulation_id",
        )
        seed = getattr(adapter, "seed")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise WorldModelError("environment adapter seed must be integer")
        if not callable(getattr(adapter, "reset")) or not callable(
            getattr(adapter, "step")
        ):
            raise WorldModelError(
                "environment adapter reset/step must be callable"
            )
        if (
            isinstance(max_steps, bool)
            or not isinstance(max_steps, int)
            or max_steps < 1
        ):
            raise WorldModelError("max_steps must be positive")
        if (
            isinstance(max_cases, bool)
            or not isinstance(max_cases, int)
            or max_cases < 1
        ):
            raise WorldModelError("max_cases must be positive")
        self.adapter = adapter
        self.simulation_id = simulation_id
        self.seed = seed
        self.assumptions = assumptions or AssumptionSet(())
        if not isinstance(self.assumptions, AssumptionSet):
            raise TypeError("assumptions must be AssumptionSet")
        self.uncertainty_policy = (
            uncertainty_policy or UncertaintyPropagationPolicy()
        )
        if not isinstance(
            self.uncertainty_policy,
            UncertaintyPropagationPolicy,
        ):
            raise TypeError(
                "uncertainty_policy must be UncertaintyPropagationPolicy"
            )
        self.max_steps = max_steps
        self.max_cases = max_cases

    @staticmethod
    def _evidence_digest(transition: EnvironmentTransition) -> str:
        evidence = transition.evidence
        return _digest(
            {
                "simulation_id": evidence.simulation_id,
                "step_index": evidence.step_index,
                "seed": evidence.seed,
                "prior_state_digest": evidence.prior_state_digest,
                "action_digest": evidence.action_digest,
                "next_state_digest": evidence.next_state_digest,
                "uncertainty": float(evidence.uncertainty),
                "evidence_class": evidence.evidence_class,
            },
            "transition evidence",
        )

    def _verify_transition(
        self,
        *,
        expected_adapter_step: int,
        prior_state: Mapping[str, object],
        action: Mapping[str, object],
        transition: EnvironmentTransition,
    ) -> None:
        if not isinstance(transition, EnvironmentTransition):
            raise WorldModelError(
                "environment step must return EnvironmentTransition"
            )
        evidence = transition.evidence
        if evidence.evidence_class != "simulation":
            raise WorldModelError(
                "environment evidence attempted to escape simulation class"
            )
        if evidence.simulation_id != self.simulation_id:
            raise WorldModelError("simulation_id drift in transition evidence")
        if evidence.seed != self.seed:
            raise WorldModelError("seed drift in transition evidence")
        if evidence.step_index != expected_adapter_step:
            raise WorldModelError("step index drift in transition evidence")
        expected_prior = _mapping_digest(prior_state, "prior state")
        expected_action = _mapping_digest(action, "action")
        expected_next = _mapping_digest(
            transition.state,
            "next state",
        )
        if evidence.prior_state_digest != expected_prior:
            raise WorldModelError(
                "transition prior-state digest mismatch"
            )
        if evidence.action_digest != expected_action:
            raise WorldModelError("transition action digest mismatch")
        if evidence.next_state_digest != expected_next:
            raise WorldModelError(
                "transition next-state digest mismatch"
            )
        if not isinstance(transition.terminal, bool):
            raise WorldModelError("transition terminal flag must be boolean")
        _finite(transition.reward, "transition reward")
        _unit(evidence.uncertainty, "transition uncertainty")

    def rollout(
        self,
        actions: Sequence[Mapping[str, object]],
        *,
        reset: bool = True,
    ) -> SimulationResult:
        if isinstance(actions, (str, bytes)) or not isinstance(
            actions,
            Sequence,
        ):
            raise WorldModelError("actions must be a sequence")
        if len(actions) > self.max_steps:
            raise WorldModelError("rollout exceeds max_steps")
        if reset:
            initial_state = self.adapter.reset()
        else:
            initial_state = self.adapter.state
        if not isinstance(initial_state, Mapping):
            raise WorldModelError("environment state must be a mapping")
        initial_digest = _mapping_digest(
            initial_state,
            "initial state",
        )
        prior_state = dict(initial_state)
        cumulative = self.assumptions.aggregate_uncertainty
        steps: list[SimulationStep] = []
        terminal = False
        expected_adapter_step: int | None = 0 if reset else None

        for index, raw_action in enumerate(actions):
            if terminal:
                break
            if not isinstance(raw_action, Mapping):
                raise WorldModelError("each action must be a mapping")
            action = dict(raw_action)
            _mapping_digest(action, "action")
            transition = self.adapter.step(action)
            if expected_adapter_step is None:
                expected_adapter_step = transition.evidence.step_index
            self._verify_transition(
                expected_adapter_step=expected_adapter_step,
                prior_state=prior_state,
                action=action,
                transition=transition,
            )
            expected_adapter_step += 1
            local = float(transition.evidence.uncertainty)
            cumulative = self.uncertainty_policy.combine(
                cumulative,
                local,
            )
            step = SimulationStep(
                step_index=index,
                action_digest=transition.evidence.action_digest,
                prior_state_digest=(
                    transition.evidence.prior_state_digest
                ),
                next_state_digest=(
                    transition.evidence.next_state_digest
                ),
                reward=float(transition.reward),
                terminal=transition.terminal,
                local_uncertainty=local,
                cumulative_uncertainty=cumulative,
                evidence_digest=self._evidence_digest(transition),
            )
            steps.append(step)
            prior_state = dict(transition.state)
            terminal = transition.terminal

        final_state = self.adapter.state
        if not isinstance(final_state, Mapping):
            raise WorldModelError("environment final state must be a mapping")
        final_digest = _mapping_digest(final_state, "final state")
        return SimulationResult(
            simulation_id=self.simulation_id,
            seed=self.seed,
            assumption_set_digest=self.assumptions.digest,
            uncertainty_policy_digest=self.uncertainty_policy.digest,
            initial_state_digest=initial_digest,
            final_state_digest=final_digest,
            steps=tuple(steps),
            cumulative_uncertainty=cumulative,
            terminal=terminal,
        )

    def compare(
        self,
        cases: Mapping[str, Sequence[Mapping[str, object]]],
    ) -> tuple[CounterfactualResult, ...]:
        if not isinstance(cases, Mapping):
            raise WorldModelError("cases must be a mapping")
        if len(cases) > self.max_cases:
            raise WorldModelError("counterfactual case count exceeds max_cases")
        normalized: list[tuple[str, Sequence[Mapping[str, object]]]] = []
        for raw_case_id, actions in cases.items():
            case_id = _token(raw_case_id, "case_id", maximum=128)
            if any(existing == case_id for existing, _ in normalized):
                raise WorldModelError("duplicate canonical case_id")
            normalized.append((case_id, actions))
        results = [
            CounterfactualResult(
                case_id=case_id,
                result=self.rollout(actions, reset=True),
            )
            for case_id, actions in sorted(normalized)
        ]
        return tuple(results)


__all__ = [
    "WORLD_MODEL_SCHEMA",
    "Assumption",
    "AssumptionSet",
    "CounterfactualResult",
    "CounterfactualRolloutEngine",
    "EnvironmentAdapter",
    "SimulationResult",
    "SimulationStep",
    "UncertaintyPropagationPolicy",
    "WorldModelError",
    "WorldState",
]
