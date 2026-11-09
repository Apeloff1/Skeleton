from __future__ import annotations

import pytest

from skeleton.jeeves.agent.causal_ensemble import (
    BayesianCausalEnsemble,
    CausalModelHypothesis,
    EnsemblePolicy,
    RobustObjective,
)
from skeleton.jeeves.agent.causal_epistemics import (
    CategoricalDistribution,
    CausalMechanism,
    CausalVariable,
    EpistemicAction,
    MechanismRow,
    Preference,
    StructuralCausalModel,
    VariableRole,
)
from skeleton.jeeves.agent.types import RiskTier


def _binary(p_one: float) -> CategoricalDistribution:
    return CategoricalDistribution({"0": 1.0 - p_one, "1": p_one}, ("0", "1"))


def _model(*, x1_y1: float, x0_y1: float = 0.1) -> StructuralCausalModel:
    model = StructuralCausalModel(max_joint_states=128)
    model.add_variable(
        CausalVariable(
            "x",
            ("0", "1"),
            role=VariableRole.ACTION,
            manipulable=True,
            risk=RiskTier.REVERSIBLE,
        )
    )
    model.add_variable(
        CausalVariable(
            "y",
            ("0", "1"),
            role=VariableRole.OUTCOME,
        )
    )
    model.set_mechanism(
        CausalMechanism(
            child_id="y",
            parent_ids=("x",),
            rows=(
                MechanismRow((("x", "0"),), _binary(x0_y1)),
                MechanismRow((("x", "1"),), _binary(x1_y1)),
            ),
            fallback=_binary(0.5),
        )
    )
    return model


def _ensemble() -> BayesianCausalEnsemble:
    optimistic = CausalModelHypothesis("optimistic", _model(x1_y1=0.9))
    pessimistic = CausalModelHypothesis("pessimistic", _model(x1_y1=0.2))
    preference = Preference(
        "y",
        CategoricalDistribution({"0": 0.05, "1": 0.95}, ("0", "1")),
        weight=1.0,
    )
    return BayesianCausalEnsemble(
        (optimistic, pessimistic),
        preferences=(preference,),
        policy=EnsemblePolicy(
            posterior_temperature=1.0,
            lower_confidence_k=1.0,
            cvar_alpha=0.5,
            stale_seconds=1000.0,
        ),
        clock=lambda: 100.0,
    )


def test_initial_posterior_is_normalized() -> None:
    ensemble = _ensemble()
    posterior = ensemble.posterior()
    assert posterior.weights["optimistic"] == pytest.approx(0.5)
    assert posterior.weights["pessimistic"] == pytest.approx(0.5)
    assert posterior.effective_model_count == pytest.approx(2.0)


def test_verified_outcome_like_update_favors_predictive_model() -> None:
    ensemble = _ensemble()
    update = ensemble.update(
        {"y": "1"},
        interventions={"x": "1"},
    )
    posterior = ensemble.posterior()
    assert posterior.weights["optimistic"] > posterior.weights["pessimistic"]
    assert update.surprise_bits > 0.0
    assert update.posterior_fingerprint == posterior.fingerprint


def test_repeated_evidence_concentrates_posterior() -> None:
    ensemble = _ensemble()
    for _ in range(5):
        ensemble.update({"y": "1"}, interventions={"x": "1"})
    posterior = ensemble.posterior()
    assert posterior.weights["optimistic"] > 0.95
    assert posterior.effective_model_count < 1.3


def test_ensemble_prediction_separates_epistemic_and_aleatoric_uncertainty() -> None:
    ensemble = _ensemble()
    prediction = ensemble.predict("y", interventions={"x": "1"})
    assert prediction.total_entropy_bits >= prediction.expected_aleatoric_entropy_bits
    assert prediction.epistemic_information_bits > 0.0
    assert prediction.maximum_pairwise_js_bits > 0.0
    assert sum(prediction.mixture.values.values()) == pytest.approx(1.0)


def test_identical_models_have_near_zero_epistemic_disagreement() -> None:
    first = CausalModelHypothesis("first", _model(x1_y1=0.8))
    second = CausalModelHypothesis("second", _model(x1_y1=0.8))
    ensemble = BayesianCausalEnsemble((first, second), clock=lambda: 10.0)
    prediction = ensemble.predict("y", interventions={"x": "1"})
    assert prediction.epistemic_information_bits == pytest.approx(0.0, abs=1e-10)
    assert prediction.maximum_pairwise_js_bits == pytest.approx(0.0, abs=1e-10)


def test_robust_objectives_are_more_conservative_than_mean() -> None:
    ensemble = _ensemble()
    action = EpistemicAction(
        "set-x1",
        interventions={"x": "1"},
        observation_targets=("y",),
        risk=RiskTier.REVERSIBLE,
    )
    mean = ensemble.evaluate_action(action, objective=RobustObjective.MEAN)
    lower = ensemble.evaluate_action(action, objective=RobustObjective.LOWER_CONFIDENCE)
    minimax = ensemble.evaluate_action(action, objective=RobustObjective.MINIMAX)
    cvar = ensemble.evaluate_action(action, objective=RobustObjective.CVAR)
    assert lower.robust_score <= mean.robust_score
    assert minimax.robust_score <= mean.robust_score
    assert cvar.robust_score <= mean.robust_score
    assert lower.standard_deviation > 0.0


def test_information_directed_score_values_model_discrimination() -> None:
    ensemble = _ensemble()
    informative = EpistemicAction(
        "informative",
        interventions={"x": "1"},
        observation_targets=("y",),
        risk=RiskTier.REVERSIBLE,
    )
    silent = EpistemicAction(
        "silent",
        interventions={"x": "0"},
        observation_targets=(),
        risk=RiskTier.REVERSIBLE,
    )
    informative_eval = ensemble.evaluate_action(
        informative,
        objective=RobustObjective.INFORMATION_DIRECTED,
    )
    silent_eval = ensemble.evaluate_action(
        silent,
        objective=RobustObjective.INFORMATION_DIRECTED,
    )
    assert informative_eval.model_information_gain_bits > 0.0
    assert silent_eval.model_information_gain_bits == 0.0


def test_experiment_design_prefers_disagreement_and_respects_risk() -> None:
    ensemble = _ensemble()
    safe = EpistemicAction(
        "safe-x1",
        interventions={"x": "1"},
        observation_targets=("y",),
        risk=RiskTier.REVERSIBLE,
        base_cost=0.01,
    )
    risky = EpistemicAction(
        "risky-x1",
        interventions={"x": "1"},
        observation_targets=("y",),
        risk=RiskTier.HIGH_IMPACT,
        reversible=False,
    )
    experiments = ensemble.design_experiments(
        (safe, risky),
        maximum_risk=RiskTier.REVERSIBLE,
    )
    assert experiments
    assert all(item.action.action_id != "risky-x1" for item in experiments)
    assert experiments[0].expected_model_information_gain_bits > 0.0


def test_rank_actions_respects_maximum_risk() -> None:
    ensemble = _ensemble()
    read = EpistemicAction("read", interventions={"x": "0"}, risk=RiskTier.READ_ONLY)
    external = EpistemicAction("external", interventions={"x": "1"}, risk=RiskTier.EXTERNAL)
    ranking = ensemble.rank_actions(
        (read, external),
        maximum_risk=RiskTier.READ_ONLY,
    )
    assert [item.action_id for item in ranking] == ["read"]


def test_posterior_health_detects_concentration() -> None:
    ensemble = _ensemble()
    for _ in range(8):
        ensemble.update({"y": "1"}, interventions={"x": "1"})
    health = ensemble.health()
    assert health.maximum_weight > 0.99
    assert health.collapsed
    assert "collapsed" in " ".join(health.reasons)


def test_posterior_snapshots_are_immutable_history() -> None:
    ensemble = _ensemble()
    before = ensemble.posterior()
    ensemble.update({"y": "1"}, interventions={"x": "1"})
    after = ensemble.posterior()
    assert before.fingerprint != after.fingerprint
    snapshots = ensemble.snapshots()
    assert len(snapshots) >= 3
    assert snapshots[-1].fingerprint == after.fingerprint


def test_model_reliability_influences_posterior_update() -> None:
    strong = CausalModelHypothesis("strong", _model(x1_y1=0.7), reliability=1.0)
    weak = CausalModelHypothesis("weak", _model(x1_y1=0.7), reliability=0.3)
    ensemble = BayesianCausalEnsemble((strong, weak), clock=lambda: 1.0)
    ensemble.update({"y": "1"}, interventions={"x": "1"})
    posterior = ensemble.posterior()
    assert posterior.weights["strong"] > posterior.weights["weak"]


def test_posterior_fingerprint_changes_only_with_state() -> None:
    ensemble = _ensemble()
    first = ensemble.posterior().fingerprint
    second = ensemble.posterior().fingerprint
    assert first == second
    ensemble.update({"y": "0"}, interventions={"x": "1"})
    assert ensemble.posterior().fingerprint != first


def test_summary_exposes_model_uncertainty_without_promoting_prediction_to_fact() -> None:
    ensemble = _ensemble()
    summary = ensemble.summary()
    assert summary["hypotheses"] == 2
    assert summary["effective_model_count"] == pytest.approx(2.0)
    assert "weights" in summary
    prediction = ensemble.predict("y", interventions={"x": "1"})
    assert prediction.fingerprint
    # Prediction objects have no EvidenceRef/evidence-promotion field by design.
    assert not hasattr(prediction, "evidence")
