"""A second registration does not erase a component kind."""

import pytest

from skeleton.forge.universal import Forge, Port
from skeleton.kernel.errors import BlueprintError


def test_a_kind_cannot_be_replaced_or_left_portless() -> None:
    forge = Forge()
    with pytest.raises(BlueprintError):
        forge.register_kind("source", (Port("out", "event", "out"),))
    with pytest.raises(BlueprintError):
        forge.register_kind("marker", ())
    with pytest.raises(BlueprintError):
        forge.register_kind("pair", (Port("in", "event", "in"), Port("in", "event", "out")))
    blueprint = forge.new_blueprint("demo")
    with pytest.raises(BlueprintError):
        forge.instantiate(blueprint, "source", "in", config="not-an-object")
    made = forge.instantiate(blueprint, "source", "in")
    assert made.instance_id == "in"
    assert [port.name for port in made.ports] == ["out"]
