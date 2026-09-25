"""A boolean flag is not a numeric parent in a structural equation."""

from skeleton.intelligence.causal import CausalGraph, CausalVariable
from skeleton.intelligence.counterfactual import StructuralModel


def test_boolean_parent_does_not_get_a_slope() -> None:
    graph = CausalGraph()
    graph.variables["flag"] = CausalVariable("flag", [False, True])
    graph.variables["y"] = CausalVariable("y", [0, 1], parents=["flag"])
    model = StructuralModel.fit(graph, [
        {"flag": False, "y": 0},
        {"flag": True, "y": 1},
        {"flag": True, "y": 3},
    ])
    assert model.coefficients["y"]["flag"] == 0.0
