from __future__ import annotations

import math

import pytest

from skeleton.jeeves.agent.causal_epistemics import (
    ActiveInferencePlanner,
    BeliefUpdater,
    CategoricalDistribution,
    CausalDiscoveryEngine,
    CausalEpistemicError,
    CausalEpistemicKernel,
    CausalMechanism,
    CausalVariable,
    EpistemicAction,
    ExperimentPurpose,
    MechanismDriftDetector,
    MechanismLearner,
    MechanismRow,
    MechanismStatus,
    Preference,
    QueryKind,
    StructuralCausalModel,
    TransitionSample,
    VariableRole,
    entropy_bits,
    js_divergence_bits,
    kl_divergence_bits,
)
from skeleton.jeeves.agent.types import RiskTier


def _binary(values=(0.5, 0.5)) -> CategoricalDistribution:
    return CategoricalDistribution({"0": values[0], "1": values[1]}, ("0", "1"))


def _confounded_model() -> StructuralCausalModel:
    """U -> X, U -> Y, X -> Y with all variables binary."""
    model = StructuralCausalModel(max_joint_states=256)
    model.add_variable(
        CausalVariable(
            "u",
            ("0", "1"),
            role=VariableRole.LATENT,
            prior=_binary((0.5, 0.5)),
            observable=False,
        )
    )
    model.add_variable(
        CausalVariable(
            "x",
            ("0", "1"),
            role=VariableRole.ACTION,
            prior=_binary((0.5, 0.5)),
            manipulable=True,
            intervention_cost=0.1,
            risk=RiskTier.REVERSIBLE,
        )
    )
    model.add_variable(
        CausalVariable(
            "y",
            ("0", "1"),
            role=VariableRole.OUTCOME,
            prior=_binary((0.5, 0.5)),
        )
    )
    model.set_mechanism(
        CausalMechanism(
            child_id="x",
            parent_ids=("u",),
            rows=(
                MechanismRow((("u", "0"),), _binary((0.9, 0.1))),
                MechanismRow((("u", "1"),), _binary((0.1, 0.9))),
            ),
            fallback=_binary(),
        )
    )
    model.set_mechanism(
        CausalMechanism(
            child_id="y",
            parent_ids=("u", "x"),
            rows=(
                MechanismRow((("u", "0"), ("x", "0")), _binary((0.95, 0.05))),
                MechanismRow((("u", "0"), ("x", "1")), _binary((0.60, 0.40))),
                MechanismRow((("u", "1"), ("x", "0")), _binary((0.50, 0.50))),
                MechanismRow((("u", "1"), ("x", "1")), _binary((0.05, 0.95))),
            ),
            fallback=_binary(),
        )
    )
    return model


def test_distribution_normalizes_and_reports_entropy() -> None:
    distribution = CategoricalDistribution({"a": 2.0, "b": 2.0}, ("a", "b"))
    assert distribution.values == {"a": 0.5, "b": 0.5}
    assert distribution.mode in {"a", "b"}
    assert distribution.entropy_bits == pytest.approx(1.0)


def test_information_metrics_are_zero_on_identity() -> None:
    p = {"a": 0.2, "b": 0.8}
    assert kl_divergence_bits(p, p) == pytest.approx(0.0, abs=1e-9)
    assert js_divergence_bits(p, p) == pytest.approx(0.0, abs=1e-9)
    assert entropy_bits({"a": 1.0, "b": 0.0}) == pytest.approx(0.0)


def test_observation_and_intervention_are_not_collapsed() -> None:
    model = _confounded_model()
    observational = model.marginal("y", evidence={"x": "1"})
    interventional = model.marginal("y", interventions={"x": "1"})
    assert abs(
        observational.probability_of("1") - interventional.probability_of("1")
    ) > 0.05


def test_intervention_forces_manipulated_variable() -> None:
    model = _confounded_model()
    result = model.infer(interventions={"x": "0"})
    assert result.query_kind is QueryKind.INTERVENTIONAL
    assert all(state.assignment["x"] == "0" for state in result.states)
    assert sum(state.probability for state in result.states) == pytest.approx(1.0)


def test_nonmanipulable_intervention_is_rejected() -> None:
    model = _confounded_model()
    with pytest.raises(CausalEpistemicError):
        model.infer(interventions={"y": "1"})


def test_markov_blanket_and_descendants_are_structural() -> None:
    model = _confounded_model()
    assert set(model.descendants("u")) == {"x", "y"}
    assert set(model.markov_blanket("x")) == {"u", "y"}


def test_belief_update_conditions_hidden_state() -> None:
    model = _confounded_model()
    updater = BeliefUpdater(model, clock=lambda: 10.0)
    prior = updater.from_evidence({})
    posterior = updater.update(prior, {"x": "1"})
    assert posterior.version == prior.version + 1
    assert posterior.marginals["u"].probability_of("1") > 0.5
    assert posterior.fingerprint != prior.fingerprint


def test_counterfactual_is_explicitly_not_identified_without_noise_model() -> None:
    model = _confounded_model()
    estimate = model.counterfactual(
        "y",
        factual_evidence={"x": "1", "y": "1"},
        intervention={"x": "0"},
    )
    assert estimate.identified is False
    assert "exogenous" in estimate.identification_note
    assert math.isclose(sum(estimate.distribution.values.values()), 1.0)


def test_active_inference_combines_preferences_and_information() -> None:
    model = _confounded_model()
    preferences = (
        Preference("y", CategoricalDistribution({"0": 0.05, "1": 0.95}, ("0", "1"))),
    )
    planner = ActiveInferencePlanner(model, preferences)
    actions = (
        EpistemicAction(
            "observe-x1",
            interventions={"x": "1"},
            observation_targets=("y",),
            risk=RiskTier.REVERSIBLE,
            reversible=True,
        ),
        EpistemicAction(
            "observe-x0",
            interventions={"x": "0"},
            observation_targets=("y",),
            risk=RiskTier.REVERSIBLE,
            reversible=True,
        ),
    )
    ranked = planner.rank(actions)
    assert len(ranked) == 2
    assert ranked[0].expected_free_energy <= ranked[1].expected_free_energy
    assert ranked[0].information_gain_bits >= 0.0
    assert ranked[0].fingerprint


def test_active_inference_respects_maximum_risk() -> None:
    model = _confounded_model()
    planner = ActiveInferencePlanner(model)
    safe = EpistemicAction("safe", interventions={"x": "0"}, risk=RiskTier.REVERSIBLE)
    risky = EpistemicAction(
        "risky",
        interventions={"x": "1"},
        risk=RiskTier.HIGH_IMPACT,
        reversible=False,
    )
    ranked = planner.rank((safe, risky), maximum_risk=RiskTier.REVERSIBLE)
    assert [item.action_id for item in ranked] == ["safe"]


def _sample(
    index: int,
    *,
    x: str,
    y: str,
    intervened: bool,
    verified: bool = True,
) -> TransitionSample:
    return TransitionSample(
        sample_id=f"sample-{index}",
        before={"x": x},
        interventions={"x": x} if intervened else {},
        after={"x": x, "y": y},
        verified=verified,
        observed_at=float(index),
    )


def test_mechanism_learner_uses_only_verified_samples() -> None:
    model = StructuralCausalModel()
    model.add_variable(
        CausalVariable("x", ("0", "1"), role=VariableRole.ACTION, manipulable=True)
    )
    model.add_variable(CausalVariable("y", ("0", "1"), role=VariableRole.OUTCOME))
    samples = [
        _sample(1, x="0", y="0", intervened=True),
        _sample(2, x="0", y="0", intervened=True),
        _sample(3, x="1", y="1", intervened=True),
        _sample(4, x="1", y="1", intervened=True),
        _sample(5, x="1", y="0", intervened=True, verified=False),
        _sample(6, x="1", y="0", intervened=True, verified=False),
    ]
    learner = MechanismLearner(model, minimum_samples=4, laplace=0.1)
    proposal = learner.fit("y", ("x",), samples, holdout_fraction=0.0)
    assert proposal.accepted_for_review
    assert proposal.mechanism.sample_count == 4
    x1 = proposal.mechanism.distribution_for({"x": "1"})
    assert x1.probability_of("1") > x1.probability_of("0")


def test_mechanism_learner_refuses_tiny_dataset() -> None:
    model = StructuralCausalModel()
    model.add_variable(
        CausalVariable("x", ("0", "1"), role=VariableRole.ACTION, manipulable=True)
    )
    model.add_variable(CausalVariable("y", ("0", "1"), role=VariableRole.OUTCOME))
    learner = MechanismLearner(model, minimum_samples=4)
    proposal = learner.fit("y", ("x",), [_sample(1, x="0", y="0", intervened=True)])
    assert not proposal.accepted_for_review
    assert proposal.confidence == 0.0
    assert proposal.mechanism.status is MechanismStatus.PROVISIONAL


def test_drift_detector_finds_large_distribution_change() -> None:
    baseline = CausalMechanism(
        child_id="y",
        parent_ids=("x",),
        rows=(MechanismRow((("x", "0"),), _binary((0.95, 0.05))),),
        fallback=_binary(),
    )
    candidate = CausalMechanism(
        child_id="y",
        parent_ids=("x",),
        rows=(MechanismRow((("x", "0"),), _binary((0.05, 0.95))),),
        fallback=_binary(),
        version=2,
    )
    drift = MechanismDriftDetector().compare(baseline, candidate, threshold_bits=0.10)
    assert drift.drift_detected
    assert drift.maximum_js_divergence_bits > 0.10


def test_causal_discovery_prefers_interventional_effect() -> None:
    model = StructuralCausalModel()
    model.add_variable(
        CausalVariable("x", ("0", "1"), role=VariableRole.ACTION, manipulable=True)
    )
    model.add_variable(CausalVariable("y", ("0", "1"), role=VariableRole.OUTCOME))
    samples = []
    for index in range(1, 11):
        samples.append(_sample(index, x="0", y="0", intervened=True))
    for index in range(11, 21):
        samples.append(_sample(index, x="1", y="1", intervened=True))
    hypothesis = CausalDiscoveryEngine(model).score_edge("x", "y", samples)
    assert hypothesis.intervention_support == 20
    assert hypothesis.interventional_effect > 0.5
    assert hypothesis.confidence > 0.0


def test_kernel_simulations_never_masquerade_as_evidence() -> None:
    model = _confounded_model()
    kernel = CausalEpistemicKernel(model, clock=lambda: 50.0)
    action = EpistemicAction(
        "simulate-x1",
        interventions={"x": "1"},
        observation_targets=("y",),
        risk=RiskTier.REVERSIBLE,
    )
    record = kernel.simulate(action)
    assert record.is_simulation is True
    assert "never promote" in record.note
    assert record.query_kind is QueryKind.INTERVENTIONAL
    assert kernel.summary()["simulations"] == 1


def test_kernel_mechanism_promotion_is_guarded() -> None:
    model = StructuralCausalModel()
    model.add_variable(
        CausalVariable("x", ("0", "1"), role=VariableRole.ACTION, manipulable=True)
    )
    model.add_variable(CausalVariable("y", ("0", "1"), role=VariableRole.OUTCOME))
    kernel = CausalEpistemicKernel(model)
    for index in range(1, 7):
        kernel.record_transition(
            _sample(index, x="0" if index < 4 else "1", y="0" if index < 4 else "1", intervened=True)
        )
    proposal = kernel.learn_mechanism("y", ("x",), minimum_samples=4)
    with pytest.raises(CausalEpistemicError):
        kernel.promote_mechanism(proposal, minimum_confidence=0.95)


def test_kernel_edge_discovery_and_experiment_design_are_bounded() -> None:
    model = StructuralCausalModel()
    model.add_variable(
        CausalVariable(
            "x",
            ("0", "1"),
            role=VariableRole.ACTION,
            manipulable=True,
            risk=RiskTier.REVERSIBLE,
        )
    )
    model.add_variable(CausalVariable("y", ("0", "1"), role=VariableRole.OUTCOME))
    kernel = CausalEpistemicKernel(model)
    for index in range(1, 9):
        kernel.record_transition(
            _sample(index, x="0", y="0", intervened=True)
        )
    for index in range(9, 17):
        kernel.record_transition(
            _sample(index, x="1", y="1", intervened=True)
        )
    hypotheses = kernel.discover_edges(limit=8)
    assert len(hypotheses) <= 8
    experiments = kernel.propose_experiments(
        maximum_risk=RiskTier.REVERSIBLE,
        limit=4,
    )
    assert len(experiments) <= 4
    assert all(item.purpose is ExperimentPurpose.DISCRIMINATE_EDGE for item in experiments)
    assert all(item.action.risk is not RiskTier.HIGH_IMPACT for item in experiments)


def test_decision_regret_audit_compares_alternatives() -> None:
    model = _confounded_model()
    kernel = CausalEpistemicKernel(
        model,
        preferences=(
            Preference("y", CategoricalDistribution({"0": 0.05, "1": 0.95}, ("0", "1"))),
        ),
    )
    actions = (
        EpistemicAction("x0", interventions={"x": "0"}, observation_targets=("y",)),
        EpistemicAction("x1", interventions={"x": "1"}, observation_targets=("y",)),
    )
    evaluations = kernel.recommend(actions)
    chosen = evaluations[-1]
    audit = kernel.audit_decision(chosen.action_id, evaluations)
    assert audit.counterfactual_regret >= 0.0
    assert audit.best_alternative_id is not None
    assert audit.fingerprint
