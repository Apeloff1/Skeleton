"""A dependency string is not four systems, and a boolean is not a cost."""

import pytest

from skeleton.forge.planner import MaterialisationPlanner
from skeleton.kernel.errors import BlueprintError


def test_a_dependency_string_and_a_boolean_cost_are_refused() -> None:
    planner = MaterialisationPlanner()
    with pytest.raises(BlueprintError):
        planner.plan({"name": "demo", "systems": [{"id": "core", "depends_on": "core"}]})
    with pytest.raises(BlueprintError):
        planner.plan({"name": "demo", "systems": [{"id": "core", "depends_on": ["missing"]}]})
    with pytest.raises(BlueprintError):
        planner.plan({"name": "demo", "systems": [{"id": "core", "declared_cost": True}]})
    plan = planner.plan({
        "name": "demo",
        "systems": [
            {"id": "in", "declared_cost": 1},
            {"id": "out", "depends_on": ["in"], "declared_cost": 2},
        ],
    })
    assert plan.waves[0].systems == ("in",)
    assert plan.waves[1].systems == ("out",)
    assert plan.critical_path == ["in", "out"]
    assert plan.total_declared_cost == 3
