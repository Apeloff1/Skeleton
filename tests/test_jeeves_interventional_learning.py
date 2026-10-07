from __future__ import annotations

import pytest

from skeleton.jeeves.agent.causal_epistemics import (
    CausalVariable,
    StructuralCausalModel,
    TransitionSample,
    VariableRole,
)
from skeleton.jeeves.agent.interventional_learning import (
    BayesianMechanismTrainer,
    InterventionalLearningError,
    InterventionalSampleResolver,
    MechanismTrainingPolicy,
    promote_training_report,
)
from skeleton.jeeves.agent.types import RiskTier


def _model() -> StructuralCausalModel:
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
    model.add_variable(
        CausalVariable("z", ("0", "1"), role=VariableRole.STATE)
    )
    model.add_variable(
        CausalVariable("y", ("0", "1"), role=VariableRole.OUTCOME)
    )
    return model


def _sample(
    index: int,
    *,
    x: str,
    y: str,
    z: str = "0",
    intervene_x: bool = True,
    intervene_y: bool = False,
    verified: bool = True,
    weight: float = 1.0,
) -> TransitionSample:
    interventions = {}
    if intervene_x:
        interventions["x"] = x
    if intervene_y:
        interventions["y"] = y
    return TransitionSample(
        sample_id=f"s-{index}",
        before={"x": "1" if x == "0" else "0", "z": z},
        interventions=interventions,
        after={"x": x, "z": z, "y": y},
        verified=verified,
        weight=weight,
        observed_at=float(index),
    )


def _policy(**overrides) -> MechanismTrainingPolicy:
    values = dict(
        equivalent_sample_size=2.0,
        minimum_train_samples=6,
        minimum_effective_sample_size=5.0,
        minimum_interventional_parent_samples=2,
        holdout_fraction=0.2,
        minimum_confidence=0.20,
        maximum_log_loss=4.0,
        maximum_brier_score=0.5,
        maximum_ece=0.5,
        calibration_bins=5,
    )
    values.update(overrides)
    return MechanismTrainingPolicy(**values)


def test_intervened_parent_is_authoritative_parent_assignment() -> None:
    sample = _sample(1, x="0", y="0", intervene_x=True)
    resolved = InterventionalSampleResolver().resolve(
        sample,
        child_id="y",
        parent_ids=("x",),
        child_domain=("0", "1"),
        parent_domains={"x": ("0", "1")},
    )
    assert resolved is not None
    assert dict(resolved.parent_assignment)["x"] == "0"
    assert resolved.parent_intervened


def test_child_intervention_is_excluded_from_natural_mechanism() -> None:
    sample = _sample(1, x="1", y="1", intervene_y=True)
    resolved = InterventionalSampleResolver().resolve(
        sample,
        child_id="y",
        parent_ids=("x",),
        child_domain=("0", "1"),
        parent_domains={"x": ("0", "1")},
    )
    assert resolved is None


def test_unverified_transition_is_excluded() -> None:
    sample = _sample(1, x="1", y="1", verified=False)
    resolved = InterventionalSampleResolver().resolve(
        sample,
        child_id="y",
        parent_ids=("x",),
        child_domain=("0", "1"),
        parent_domains={"x": ("0", "1")},
    )
    assert resolved is None


def test_trainer_learns_parent_intervention_signal() -> None:
    model = _model()
    samples = []
    for index in range(1, 9):
        samples.append(_sample(index, x="0", y="0"))
    for index in range(9, 17):
        samples.append(_sample(index, x="1", y="1"))
    trainer = BayesianMechanismTrainer(model, policy=_policy())
    report = trainer.train("y", ("x",), samples)
    assert report.interventional_parent_samples >= 10
    assert report.excluded_child_interventions == 0
    x0 = report.mechanism.distribution_for({"x": "0"})
    x1 = report.mechanism.distribution_for({"x": "1"})
    assert x0.probability_of("0") > 0.8
    assert x1.probability_of("1") > 0.8
    assert report.effective_sample_size > 10


def test_child_interventions_do_not_poison_fit() -> None:
    model = _model()
    samples = []
    for index in range(1, 9):
        samples.append(_sample(index, x="0", y="0"))
    for index in range(9, 17):
        samples.append(_sample(index, x="1", y="1"))
    for index in range(17, 40):
        # Contradictory forced outcomes must not train y's natural mechanism.
        samples.append(_sample(index, x="1", y="0", intervene_y=True))
    trainer = BayesianMechanismTrainer(model, policy=_policy())
    report = trainer.train("y", ("x",), samples)
    assert report.excluded_child_interventions == 23
    assert report.mechanism.distribution_for({"x": "1"}).probability_of("1") > 0.8


def test_unverified_mass_does_not_change_posterior_rows() -> None:
    model = _model()
    clean = [
        *[_sample(i, x="0", y="0") for i in range(1, 8)],
        *[_sample(i, x="1", y="1") for i in range(8, 15)],
    ]
    poisoned = clean + [
        _sample(i, x="1", y="0", verified=False)
        for i in range(15, 45)
    ]
    trainer = BayesianMechanismTrainer(model, policy=_policy())
    first = trainer.train("y", ("x",), clean)
    second = trainer.train("y", ("x",), poisoned)
    assert first.mechanism.fingerprint == second.mechanism.fingerprint
    assert second.excluded_unverified == 30


def test_weighted_samples_reduce_effective_sample_size_when_concentrated() -> None:
    model = _model()
    balanced = [
        _sample(i, x="0" if i < 6 else "1", y="0" if i < 6 else "1", weight=1.0)
        for i in range(1, 11)
    ]
    concentrated = [
        _sample(i, x="0" if i < 6 else "1", y="0" if i < 6 else "1", weight=10.0 if i == 1 else 0.1)
        for i in range(1, 11)
    ]
    trainer = BayesianMechanismTrainer(model, policy=_policy(minimum_effective_sample_size=1.0))
    report_balanced = trainer.train("y", ("x",), balanced)
    report_concentrated = trainer.train("y", ("x",), concentrated)
    assert report_concentrated.effective_sample_size < report_balanced.effective_sample_size


def test_temporal_holdout_produces_probabilistic_metrics() -> None:
    model = _model()
    samples = []
    for index in range(1, 16):
        x = "0" if index % 2 == 0 else "1"
        samples.append(_sample(index, x=x, y=x))
    trainer = BayesianMechanismTrainer(model, policy=_policy())
    report = trainer.train("y", ("x",), samples)
    assert report.metrics is not None
    assert report.metrics.count >= 1
    assert report.metrics.log_loss >= 0.0
    assert 0.0 <= report.metrics.brier_score <= 1.0
    assert 0.0 <= report.metrics.expected_calibration_error <= 1.0
    assert 0.0 <= report.metrics.accuracy <= 1.0


def test_promotion_requires_interventional_parent_support() -> None:
    model = _model()
    samples = [
        _sample(i, x="0" if i < 8 else "1", y="0" if i < 8 else "1", intervene_x=False)
        for i in range(1, 15)
    ]
    trainer = BayesianMechanismTrainer(
        model,
        policy=_policy(minimum_interventional_parent_samples=2),
    )
    report = trainer.train("y", ("x",), samples)
    assert report.interventional_parent_samples == 0
    assert not report.promotable
    assert any("interventions" in reason for reason in report.reasons)


def test_promoted_mechanism_is_new_typed_revision() -> None:
    model = _model()
    samples = [
        *[_sample(i, x="0", y="0") for i in range(1, 9)],
        *[_sample(i, x="1", y="1") for i in range(9, 17)],
    ]
    trainer = BayesianMechanismTrainer(model, policy=_policy())
    report = trainer.train("y", ("x",), samples)
    assert report.promotable
    promoted = promote_training_report(report)
    assert promoted.status.value == "learned"
    assert promoted.metadata["training_report_id"] == report.report_id
    assert promoted.confidence == report.confidence


def test_parent_set_comparison_penalizes_unnecessary_structure_via_marginal_likelihood() -> None:
    model = _model()
    samples = []
    for index in range(1, 31):
        x = "0" if index % 2 == 0 else "1"
        z = "0" if index % 3 else "1"
        samples.append(_sample(index, x=x, y=x, z=z))
    trainer = BayesianMechanismTrainer(model, policy=_policy())
    ranking = trainer.compare_parent_sets("y", (("x",), ("x", "z"), ()), samples)
    assert {item.parent_ids for item in ranking} == {("x",), ("x", "z"), ()}
    x_score = next(item for item in ranking if item.parent_ids == ("x",))
    empty_score = next(item for item in ranking if item.parent_ids == ())
    assert x_score.bdeu_log_score > empty_score.bdeu_log_score


def test_invalid_parent_set_is_rejected() -> None:
    model = _model()
    trainer = BayesianMechanismTrainer(model, policy=_policy())
    with pytest.raises(InterventionalLearningError):
        trainer.train("y", ("y",), [])


def test_training_report_is_content_addressed() -> None:
    model = _model()
    samples = [
        *[_sample(i, x="0", y="0") for i in range(1, 9)],
        *[_sample(i, x="1", y="1") for i in range(9, 17)],
    ]
    trainer = BayesianMechanismTrainer(model, policy=_policy())
    first = trainer.train("y", ("x",), samples)
    second = trainer.train("y", ("x",), samples)
    assert first.fingerprint == second.fingerprint
    assert first.report_id == second.report_id
