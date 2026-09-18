from __future__ import annotations

import pytest

from skeleton.jeeves.agent.causal_epistemics import (
    CategoricalDistribution,
    CausalMechanism,
    CausalVariable,
    MechanismRow,
    StructuralCausalModel,
    VariableRole,
)
from skeleton.jeeves.agent.causal_inference import (
    EliminationHeuristic,
    Factor,
    FactorComplexityExceeded,
    InferencePolicy,
    VariableEliminationEngine,
)
from skeleton.jeeves.agent.types import RiskTier


def _binary(p_one: float) -> CategoricalDistribution:
    return CategoricalDistribution({"0": 1.0 - p_one, "1": p_one}, ("0", "1"))


def _confounded_model() -> StructuralCausalModel:
    model = StructuralCausalModel(max_joint_states=1024)
    model.add_variable(CausalVariable("u", ("0", "1"), role=VariableRole.LATENT, prior=_binary(0.5)))
    model.add_variable(CausalVariable("x", ("0", "1"), role=VariableRole.ACTION, manipulable=True, risk=RiskTier.REVERSIBLE))
    model.add_variable(CausalVariable("y", ("0", "1"), role=VariableRole.OUTCOME))
    model.set_mechanism(CausalMechanism(
        child_id="x",
        parent_ids=("u",),
        rows=(
            MechanismRow((("u", "0"),), _binary(0.1)),
            MechanismRow((("u", "1"),), _binary(0.9)),
        ),
        fallback=_binary(0.5),
    ))
    model.set_mechanism(CausalMechanism(
        child_id="y",
        parent_ids=("u", "x"),
        rows=(
            MechanismRow((("u", "0"), ("x", "0")), _binary(0.05)),
            MechanismRow((("u", "0"), ("x", "1")), _binary(0.40)),
            MechanismRow((("u", "1"), ("x", "0")), _binary(0.50)),
            MechanismRow((("u", "1"), ("x", "1")), _binary(0.95)),
        ),
        fallback=_binary(0.5),
    ))
    return model


def test_factor_condition_removes_observed_dimension() -> None:
    factor = Factor(
        ("a", "b"),
        {"a": ("0", "1"), "b": ("0", "1")},
        {
            ("0", "0"): 0.1,
            ("0", "1"): 0.2,
            ("1", "0"): 0.3,
            ("1", "1"): 0.4,
        },
    )
    conditioned = factor.condition({"a": "1"})
    assert conditioned.variables == ("b",)
    assert conditioned.values[("0",)] == pytest.approx(0.3)
    assert conditioned.values[("1",)] == pytest.approx(0.4)


def test_factor_multiplication_hash_joins_shared_variable() -> None:
    left = Factor(
        ("a", "b"),
        {"a": ("0", "1"), "b": ("0", "1")},
        {("0", "0"): 0.2, ("1", "1"): 0.8},
    )
    right = Factor(
        ("b", "c"),
        {"b": ("0", "1"), "c": ("0", "1")},
        {("0", "1"): 0.5, ("1", "0"): 0.25},
    )
    product = left.multiply(right)
    assert product.variables == ("a", "b", "c")
    assert product.values[("0", "0", "1")] == pytest.approx(0.1)
    assert product.values[("1", "1", "0")] == pytest.approx(0.2)
    assert product.entry_count == 2


def test_variable_elimination_matches_reference_enumeration() -> None:
    model = _confounded_model()
    engine = VariableEliminationEngine(model)
    reference = model.marginal("y", evidence={"x": "1"})
    scalable = engine.marginal("y", evidence={"x": "1"})
    assert scalable.values["1"] == pytest.approx(reference.values["1"], abs=1e-10)
    assert scalable.values["0"] == pytest.approx(reference.values["0"], abs=1e-10)


def test_interventional_variable_elimination_matches_reference() -> None:
    model = _confounded_model()
    engine = VariableEliminationEngine(model)
    reference = model.marginal("y", interventions={"x": "1"})
    scalable = engine.marginal("y", interventions={"x": "1"})
    assert scalable.values["1"] == pytest.approx(reference.values["1"], abs=1e-10)


def test_observation_and_do_remain_distinct() -> None:
    model = _confounded_model()
    engine = VariableEliminationEngine(model)
    observational = engine.marginal("y", evidence={"x": "1"})
    interventional = engine.marginal("y", interventions={"x": "1"})
    assert abs(observational.values["1"] - interventional.values["1"]) > 0.05


def test_ancestor_pruning_removes_irrelevant_component() -> None:
    model = _confounded_model()
    model.add_variable(CausalVariable("irrelevant-a", ("0", "1"), prior=_binary(0.5)))
    model.add_variable(CausalVariable("irrelevant-b", ("0", "1")))
    model.set_mechanism(CausalMechanism(
        child_id="irrelevant-b",
        parent_ids=("irrelevant-a",),
        rows=(
            MechanismRow((("irrelevant-a", "0"),), _binary(0.2)),
            MechanismRow((("irrelevant-a", "1"),), _binary(0.8)),
        ),
        fallback=_binary(0.5),
    ))
    result = VariableEliminationEngine(model).query(("y",), evidence={"x": "1"})
    assert "irrelevant-a" in result.diagnostics.pruned_variables
    assert "irrelevant-b" in result.diagnostics.pruned_variables
    assert set(result.diagnostics.relevant_variables) == {"u", "x", "y"}


def _chain(length: int) -> StructuralCausalModel:
    model = StructuralCausalModel(max_joint_states=32)
    for index in range(length):
        variable_id = f"v{index}"
        model.add_variable(CausalVariable(variable_id, ("0", "1"), prior=_binary(0.5)))
        if index:
            parent = f"v{index - 1}"
            model.set_mechanism(CausalMechanism(
                child_id=variable_id,
                parent_ids=(parent,),
                rows=(
                    MechanismRow(((parent, "0"),), _binary(0.1)),
                    MechanismRow(((parent, "1"),), _binary(0.9)),
                ),
                fallback=_binary(0.5),
            ))
    return model


def test_long_sparse_chain_is_tractable_when_joint_enumeration_is_not() -> None:
    model = _chain(30)
    engine = VariableEliminationEngine(
        model,
        policy=InferencePolicy(maximum_sparse_entries=100, maximum_dense_capacity=1000),
    )
    result = engine.query(("v29",), evidence={"v0": "1"})
    assert result.factor.entry_count == 2
    assert result.diagnostics.maximum_sparse_entries <= 4
    assert len(result.diagnostics.elimination_order) >= 20


def test_min_fill_and_min_degree_produce_same_marginal() -> None:
    model = _confounded_model()
    min_fill = VariableEliminationEngine(model, policy=InferencePolicy(heuristic=EliminationHeuristic.MIN_FILL))
    min_degree = VariableEliminationEngine(model, policy=InferencePolicy(heuristic=EliminationHeuristic.MIN_DEGREE))
    left = min_fill.marginal("y")
    right = min_degree.marginal("y")
    assert left.values == pytest.approx(right.values)


def test_joint_query_is_normalized() -> None:
    model = _confounded_model()
    result = VariableEliminationEngine(model).query(("u", "y"), interventions={"x": "1"})
    assert result.factor.variables == ("u", "y")
    assert sum(result.factor.values.values()) == pytest.approx(1.0)
    assert result.factor.entry_count <= 4


def test_observed_query_returns_point_distribution() -> None:
    model = _confounded_model()
    engine = VariableEliminationEngine(model)
    distribution = engine.marginal("x", evidence={"x": "1"})
    assert distribution.values["1"] == pytest.approx(1.0)
    assert distribution.values["0"] == pytest.approx(0.0)


def test_evidence_likelihood_is_nonzero_and_bounded() -> None:
    model = _confounded_model()
    engine = VariableEliminationEngine(model)
    likelihood = engine.evidence_likelihood({"x": "1", "y": "1"})
    assert 0.0 < likelihood <= 1.0


def test_complexity_guard_fails_closed() -> None:
    model = StructuralCausalModel()
    for name in ("a", "b", "c"):
        model.add_variable(CausalVariable(name, tuple(str(i) for i in range(20))))
    model.add_variable(CausalVariable("y", ("0", "1")))
    # y has a dense 20*20*20 parent table.  A deliberately tiny dense-capacity
    # guard must stop the query rather than silently approximate it.
    rows = []
    for a in model.variable("a").domain:
        for b in model.variable("b").domain:
            for c in model.variable("c").domain:
                rows.append(MechanismRow((("a", a), ("b", b), ("c", c)), _binary(0.5)))
    model.set_mechanism(CausalMechanism("y", ("a", "b", "c"), tuple(rows), _binary(0.5)))
    engine = VariableEliminationEngine(
        model,
        policy=InferencePolicy(maximum_sparse_entries=100_000, maximum_dense_capacity=1000),
    )
    with pytest.raises(FactorComplexityExceeded):
        engine.query(("y",))


def test_diagnostics_are_deterministic() -> None:
    model = _confounded_model()
    engine = VariableEliminationEngine(model)
    first = engine.query(("y",), evidence={"x": "1"})
    second = engine.query(("y",), evidence={"x": "1"})
    assert first.query_fingerprint == second.query_fingerprint
    assert first.diagnostics.fingerprint == second.diagnostics.fingerprint
