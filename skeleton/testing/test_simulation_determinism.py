from __future__ import annotations

import pytest

from skeleton.simulation.environment import DeterministicEnvironmentAdapter
from skeleton.simulation.world_model import (
    Assumption,
    AssumptionSet,
    CounterfactualRolloutEngine,
)


def _reducer(state, action, seed):
    position = int(state.get("position", 0)) + int(action.get("delta", 0))
    next_state = {
        "position": position,
        "seed": seed,
        "label": action.get("label", "none"),
    }
    uncertainty = float(action.get("uncertainty", 0.05))
    return (
        next_state,
        float(position),
        position >= int(action.get("terminal_at", 99)),
        uncertainty,
    )


def _adapter(seed: int = 7):
    return DeterministicEnvironmentAdapter(
        simulation_id="deterministic-world-model",
        initial_state={"position": 0},
        reducer=_reducer,
        seed=seed,
    )


def _engine(seed: int = 7):
    assumptions = AssumptionSet(
        (
            Assumption(
                "friction-model",
                "friction remains constant over rollout",
                0.1,
                "evidence:friction-calibration",
            ),
        )
    )
    return CounterfactualRolloutEngine(
        _adapter(seed),
        assumptions=assumptions,
    )


def test_same_seed_state_actions_and_assumptions_replay_exactly() -> None:
    actions = [
        {"delta": 1, "label": "a", "uncertainty": 0.05},
        {"delta": 2, "label": "b", "uncertainty": 0.10},
    ]

    left = _engine(11).rollout(actions)
    right = _engine(11).rollout(actions)

    assert left == right
    assert left.digest == right.digest
    assert [step.digest for step in left.steps] == [
        step.digest for step in right.steps
    ]


def test_reset_replays_same_engine_deterministically() -> None:
    engine = _engine()
    actions = [{"delta": 1}, {"delta": 1}]

    first = engine.rollout(actions)
    second = engine.rollout(actions)

    assert first.digest == second.digest
    assert first.final_state_digest == second.final_state_digest


def test_action_mapping_key_order_does_not_change_result_identity() -> None:
    left = _engine().rollout(
        [{"delta": 2, "label": "x", "uncertainty": 0.2}]
    )
    right = _engine().rollout(
        [{"uncertainty": 0.2, "label": "x", "delta": 2}]
    )

    assert left.digest == right.digest


def test_different_seed_changes_world_state_and_result_identity() -> None:
    left = _engine(1).rollout([{"delta": 1}])
    right = _engine(2).rollout([{"delta": 1}])

    assert left.final_state_digest != right.final_state_digest
    assert left.digest != right.digest


def test_terminal_transition_stops_remaining_actions() -> None:
    result = _engine().rollout(
        [
            {"delta": 1, "terminal_at": 2},
            {"delta": 1, "terminal_at": 2},
            {"delta": 100, "terminal_at": 2},
        ]
    )

    assert result.terminal is True
    assert len(result.steps) == 2


def test_counterfactual_case_order_does_not_change_case_results() -> None:
    engine = _engine()
    first = engine.compare(
        {
            "slow": [{"delta": 1}],
            "fast": [{"delta": 3}],
        }
    )
    second = engine.compare(
        {
            "fast": [{"delta": 3}],
            "slow": [{"delta": 1}],
        }
    )

    assert [item.case_id for item in first] == ["fast", "slow"]
    assert [item.digest for item in first] == [
        item.digest for item in second
    ]


def test_counterfactual_cases_reset_environment_independently() -> None:
    results = _engine().compare(
        {
            "one": [{"delta": 1}],
            "two": [{"delta": 2}],
        }
    )

    by_id = {item.case_id: item.result for item in results}
    assert by_id["one"].steps[0].reward == 1.0
    assert by_id["two"].steps[0].reward == 2.0


def test_continued_rollout_accepts_nonzero_adapter_step_offset() -> None:
    engine = _engine()

    first = engine.rollout([{"delta": 1}], reset=True)
    continued = engine.rollout([{"delta": 1}], reset=False)

    assert first.steps[0].step_index == 0
    assert continued.steps[0].step_index == 0
    assert continued.initial_state_digest == first.final_state_digest
    assert continued.final_state_digest != first.final_state_digest


def test_uncertainty_changes_result_identity_without_changing_authority_class() -> None:
    low = _engine().rollout([{"delta": 1, "uncertainty": 0.01}])
    high = _engine().rollout([{"delta": 1, "uncertainty": 0.8}])

    assert low.cumulative_uncertainty < high.cumulative_uncertainty
    assert low.digest != high.digest
    assert low.evidence_class == high.evidence_class == "simulation"


def test_local_uncertainty_sequence_is_monotonic_after_propagation() -> None:
    result = _engine().rollout(
        [
            {"delta": 1, "uncertainty": 0.1},
            {"delta": 1, "uncertainty": 0.0},
            {"delta": 1, "uncertainty": 0.2},
        ]
    )

    cumulative = [step.cumulative_uncertainty for step in result.steps]
    assert cumulative == sorted(cumulative)
    assert cumulative[1] == pytest.approx(cumulative[0])
