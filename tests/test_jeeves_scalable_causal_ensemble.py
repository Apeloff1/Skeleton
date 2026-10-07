from __future__ import annotations

import pytest

from skeleton.jeeves.agent.causal_ensemble import CausalModelHypothesis, RobustObjective
from skeleton.jeeves.agent.causal_epistemics import (
    CategoricalDistribution,
    CausalMechanism,
    CausalVariable,
    EpistemicAction,
    MechanismRow,
    Preference,
    StructuralCausalModel,
)
from skeleton.jeeves.agent.causal_inference import InferencePolicy
from skeleton.jeeves.agent.scalable_causal_ensemble import FactorizedBayesianCausalEnsemble
from skeleton.jeeves.agent.types import RiskTier


def _binary(p_one: float) -> CategoricalDistribution:
    return CategoricalDistribution({"0": 1.0 - p_one, "1": p_one}, ("0", "1"))


def _long_chain(length: int, strength: float, *, model_limit: int = 32) -> StructuralCausalModel:
    model = StructuralCausalModel(max_joint_states=model_limit)
    for index in range(length):
        name = f"v{index}"
        model.add_variable(
            CausalVariable(
                name,
                ("0", "1"),
                manipulable=index == 0,
                risk=RiskTier.REVERSIBLE if index == 0 else RiskTier.READ_ONLY,
                prior=_binary(0.5),
            )
        )
        if index:
            parent = f"v{index - 1}"
            model.set_mechanism(
                CausalMechanism(
                    child_id=name,
                    parent_ids=(parent,),
                    rows=(
                        MechanismRow(((parent, "0"),), _binary(1.0 - strength)),
                        MechanismRow(((parent, "1"),), _binary(strength)),
                    ),
                    fallback=_binary(0.5),
                )
            )
    return model


def _ensemble(length: int = 28) -> FactorizedBayesianCausalEnsemble:
    strong = CausalModelHypothesis("strong", _long_chain(length, 0.95))
    weak = CausalModelHypothesis("weak", _long_chain(length, 0.65))
    preference = Preference(
        f"v{length - 1}",
        CategoricalDistribution({"0": 0.05, "1": 0.95}, ("0", "1")),
    )
    return FactorizedBayesianCausalEnsemble(
        (strong, weak),
        preferences=(preference,),
        inference_policy=InferencePolicy(
            maximum_sparse_entries=100,
            maximum_dense_capacity=1000,
            ancestor_pruning=True,
        ),
        clock=lambda: 20.0,
    )


def test_factorized_ensemble_handles_models_whose_reference_joint_limit_is_tiny() -> None:
    ensemble = _ensemble(28)
    # Each source SCM was configured with max_joint_states=32.  Enumerating the
    # 2^28 joint would fail, while sparse elimination along the chain is tiny.
    prediction = ensemble.predict("v27", interventions={"v0": "1"})
    assert sum(prediction.mixture.values.values()) == pytest.approx(1.0)
    assert prediction.epistemic_information_bits >= 0.0


def test_factorized_posterior_update_uses_sparse_evidence_likelihood() -> None:
    ensemble = _ensemble(24)
    update = ensemble.update(
        {"v23": "1"},
        conditioning_evidence={"v1": "1"},
        interventions={"v0": "1"},
    )
    assert update.surprise_bits >= 0.0
    assert sum(ensemble.posterior().weights.values()) == pytest.approx(1.0)


def test_factorized_action_scoring_remains_robust_under_structure_uncertainty() -> None:
    ensemble = _ensemble(20)
    action = EpistemicAction(
        "drive-source",
        interventions={"v0": "1"},
        observation_targets=("v19",),
        risk=RiskTier.REVERSIBLE,
    )
    mean = ensemble.evaluate_action(action, objective=RobustObjective.MEAN)
    cvar = ensemble.evaluate_action(action, objective=RobustObjective.CVAR)
    lower = ensemble.evaluate_action(action, objective=RobustObjective.LOWER_CONFIDENCE)
    assert cvar.robust_score <= mean.robust_score
    assert lower.robust_score <= mean.robust_score
    assert mean.model_information_gain_bits >= 0.0


def test_factorized_information_gain_is_positive_when_models_disagree() -> None:
    ensemble = _ensemble(12)
    action = EpistemicAction(
        "probe",
        interventions={"v0": "1"},
        observation_targets=("v11",),
        risk=RiskTier.READ_ONLY,
    )
    evaluation = ensemble.evaluate_action(
        action,
        objective=RobustObjective.INFORMATION_DIRECTED,
    )
    assert evaluation.model_information_gain_bits > 0.0


def test_factorized_experiment_design_returns_low_risk_discriminating_probe() -> None:
    ensemble = _ensemble(10)
    safe = EpistemicAction(
        "safe",
        interventions={"v0": "1"},
        observation_targets=("v9",),
        risk=RiskTier.REVERSIBLE,
        base_cost=0.01,
    )
    risky = EpistemicAction(
        "risky",
        interventions={"v0": "0"},
        observation_targets=("v9",),
        risk=RiskTier.HIGH_IMPACT,
        reversible=False,
    )
    experiments = ensemble.design_experiments(
        (safe, risky),
        maximum_risk=RiskTier.REVERSIBLE,
    )
    assert experiments
    assert all(item.action.action_id == "safe" for item in experiments)
    assert experiments[0].expected_model_information_gain_bits > 0.0


def test_factorized_prediction_matches_small_reference_model() -> None:
    strong = _long_chain(5, 0.9, model_limit=1024)
    weak = _long_chain(5, 0.7, model_limit=1024)
    ensemble = FactorizedBayesianCausalEnsemble(
        (
            CausalModelHypothesis("strong", strong),
            CausalModelHypothesis("weak", weak),
        ),
        inference_policy=InferencePolicy(maximum_sparse_entries=1000),
        clock=lambda: 1.0,
    )
    prediction = ensemble.predict("v4", interventions={"v0": "1"})
    expected_strong = strong.marginal("v4", interventions={"v0": "1"})
    expected_weak = weak.marginal("v4", interventions={"v0": "1"})
    expected = 0.5 * expected_strong.values["1"] + 0.5 * expected_weak.values["1"]
    assert prediction.mixture.values["1"] == pytest.approx(expected, abs=1e-10)


def test_engine_cache_is_revision_sensitive() -> None:
    ensemble = _ensemble(8)
    first = ensemble.predict("v7", interventions={"v0": "1"})
    second = ensemble.predict("v7", interventions={"v0": "1"})
    assert first.fingerprint == second.fingerprint
    assert len(ensemble._engine_cache) == 2
