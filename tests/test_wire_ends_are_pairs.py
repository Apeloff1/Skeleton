"""A wire is a pair of ports, and a cycle is not a finished order."""

import pytest

from skeleton.forge.universal import Blueprint, Component, Forge, Port, Wire
from skeleton.kernel.errors import BlueprintError, MaterialisationError


def _component(instance_id: str) -> Component:
    return Component(instance_id, "transform", (Port("in", "event", "in"), Port("out", "event", "out")))


def test_a_string_is_not_a_wire_and_a_cycle_has_no_order() -> None:
    blueprint = Blueprint("bp", "demo")
    blueprint.add_component(_component("a"))
    blueprint.add_component(_component("b"))
    with pytest.raises(BlueprintError):
        blueprint.connect("ab", ("b", "in"))
    blueprint.wires.append(Wire(src="ab", dst=("b", "in")))
    assert any("wire ends" in problem for problem in blueprint.validate())
    blueprint.wires.clear()
    blueprint.connect(("a", "out"), ("b", "in"))
    blueprint.connect(("b", "out"), ("a", "in"))
    assert any("cycle" in problem for problem in blueprint.validate())
    with pytest.raises(MaterialisationError):
        Forge._topological_order(blueprint)
    blueprint.wires.clear()
    blueprint.connect(("a", "out"), ("b", "in"))
    assert Forge._topological_order(blueprint) == ["a", "b"]
