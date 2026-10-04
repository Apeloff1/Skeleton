from __future__ import annotations

from dataclasses import dataclass
import hashlib

import pytest

from skeleton.simulation.environment import (
    DeterministicEnvironmentAdapter,
    EnvironmentTransition,
    SimulationBoundaryError,
    SimulationEvidence,
)
from skeleton.simulation.world_model import (
    Assumption,
    AssumptionSet,
    CounterfactualRolloutEngine,
    UncertaintyPropagationPolicy,
    WorldModelError,
    WorldState,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _reducer(state, action, seed):
    next_state = {
        "position": int(state.get("position", 0)) + int(action.get("delta", 0)),
        "seed": seed,
    }
    return (
        next_state,
        float(action.get("reward", 0.0)),
        bool(action.get("terminal", False)),
        float(action.get("uncertainty", 0.1)),
    )


def _engine(*, assumptions: AssumptionSet | None = None, max_steps: int = 8):
    adapter = DeterministicEnvironmentAdapter(
        simulation_id="authority-boundary",
        initial_state={"position": 0},
        reducer=_reducer,
        seed=17,
    )
    return CounterfactualRolloutEngine(
        adapter,
        assumptions=assumptions,
        max_steps=max_steps,
    )


def test_assumption_set_is_canonical_and_uncertainty_accumulates() -> None:
    left = Assumption(
        "network-stable",
        "network latency remains within modeled range",
        0.20,
        "evidence:network-calibration",
    )
    right = Assumption(
        "provider-stable",
        "provider behavior remains within observed envelope",
        0.10,
        "evidence:provider-calibration",
    )

    a = AssumptionSet((right, left))
    b = AssumptionSet((left, right))

    assert a.assumptions == b.assumptions
    assert a.digest == b.digest
    assert a.aggregate_uncertainty == pytest.approx(0.28)


def test_duplicate_assumption_identity_fails_closed() -> None:
    first = Assumption("same", "first statement", 0.1, "source:first")
    second = Assumption("same", "second statement", 0.2, "source:second")

    with pytest.raises(WorldModelError, match="duplicate assumption_id"):
        AssumptionSet((first, second))


def test_uncertainty_policy_is_monotonic_and_conservative() -> None:
    policy = UncertaintyPropagationPolicy()

    first = policy.combine(0.20, 0.10)
    second = policy.combine(first, 0.30)

    assert first == pytest.approx(0.28)
    assert second == pytest.approx(0.496)
    assert second >= first
    assert second >= 0.30


def test_assumption_uncertainty_cannot_be_erased_by_zero_uncertainty_steps() -> None:
    assumptions = AssumptionSet(
        (
            Assumption(
                "model-bias",
                "the reducer may omit an unmodeled variable",
                0.4,
                "evidence:model-review",
            ),
        )
    )
    engine = _engine(assumptions=assumptions)

    result = engine.rollout(
        [
            {"delta": 1, "uncertainty": 0.0},
            {"delta": 1, "uncertainty": 0.0},
        ]
    )

    assert result.cumulative_uncertainty == pytest.approx(0.4)
    assert all(
        step.cumulative_uncertainty >= 0.4
        for step in result.steps
    )


def test_simulated_success_can_never_satisfy_real_postcondition() -> None:
    result = _engine().rollout(
        [{"delta": 1, "reward": 100.0, "terminal": True}]
    )

    assert result.terminal is True
    assert result.evidence_class == "simulation"
    assert result.can_support_real_world_fact is False
    assert result.can_satisfy_real_postcondition is False
    with pytest.raises(
        WorldModelError,
        match="cannot satisfy a real-world postcondition",
    ):
        result.require_real_world_postcondition_authority()


def test_world_state_contract_is_reused_not_redefined() -> None:
    assert WorldState.__module__ == "skeleton.simulation.world.scene"


@dataclass
class _TamperedAdapter:
    simulation_id: str = "tampered"
    seed: int = 3

    def __post_init__(self):
        self._state = {"x": 0}
        self._step = 0

    @property
    def state(self):
        return dict(self._state)

    def reset(self):
        self._state = {"x": 0}
        self._step = 0
        return self.state

    def step(self, action):
        prior = dict(self._state)
        self._state = {"x": prior["x"] + 1}
        evidence = SimulationEvidence(
            simulation_id=self.simulation_id,
            step_index=self._step,
            seed=self.seed,
            prior_state_digest=_digest("wrong-prior"),
            action_digest=hashlib.sha256(
                b'{"x":1}'
            ).hexdigest(),
            next_state_digest=hashlib.sha256(
                b'{"x":1}'
            ).hexdigest(),
            uncertainty=0.1,
        )
        self._step += 1
        return EnvironmentTransition(
            state=self.state,
            reward=1.0,
            terminal=False,
            evidence=evidence,
        )


def test_adapter_evidence_digest_mismatch_is_rejected() -> None:
    engine = CounterfactualRolloutEngine(_TamperedAdapter())

    with pytest.raises(
        WorldModelError,
        match="prior-state digest mismatch",
    ):
        engine.rollout([{"x": 1}])


def test_rollout_and_counterfactual_bounds_fail_before_unbounded_work() -> None:
    engine = _engine(max_steps=2)

    with pytest.raises(WorldModelError, match="exceeds max_steps"):
        engine.rollout([{"delta": 1}, {"delta": 1}, {"delta": 1}])

    bounded = CounterfactualRolloutEngine(
        DeterministicEnvironmentAdapter(
            simulation_id="case-bound",
            initial_state={"position": 0},
            reducer=_reducer,
            seed=1,
        ),
        max_cases=1,
    )
    with pytest.raises(WorldModelError, match="case count exceeds"):
        bounded.compare(
            {
                "a": [{"delta": 1}],
                "b": [{"delta": 2}],
            }
        )


def test_non_json_action_is_rejected_before_transition() -> None:
    engine = _engine()

    with pytest.raises(
        SimulationBoundaryError,
        match="deterministic JSON",
    ):
        engine.rollout([{"bad": object()}])
