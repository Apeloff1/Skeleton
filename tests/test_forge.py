"""Tests for the Universal Forge."""

import pytest

from skeleton.forge import Forge, Port
from skeleton.kernel.errors import BlueprintError, MaterialisationError


def make_linear(forge: Forge):
    bp = forge.new_blueprint("etl")
    forge.instantiate(bp, "source", "in")
    forge.instantiate(bp, "transform", "mid")
    forge.instantiate(bp, "sink", "out")
    bp.connect(("in", "out"), ("mid", "in"))
    bp.connect(("mid", "out"), ("out", "in"))
    return bp


class TestForge:
    def test_stdlib_kinds(self):
        assert Forge().available_kinds() == ["sink", "source", "state_store", "transform"]

    def test_materialise_order(self):
        forge = Forge()
        result = forge.materialise(make_linear(forge))
        assert result["execution_order"] == ["in", "mid", "out"]

    def test_type_mismatch_detected(self):
        forge = Forge()
        bp = forge.new_blueprint("bad")
        forge.instantiate(bp, "source", "s")
        forge.instantiate(bp, "state_store", "store")
        bp.connect(("s", "out"), ("store", "write"))  # event -> state
        problems = bp.validate()
        assert any("type mismatch" in p for p in problems)

    def test_cycle_detected(self):
        forge = Forge()
        bp = forge.new_blueprint("cyclic")
        forge.instantiate(bp, "transform", "a")
        forge.instantiate(bp, "transform", "b")
        bp.connect(("a", "out"), ("b", "in"))
        bp.connect(("b", "out"), ("a", "in"))
        assert any("cycle" in p for p in bp.validate())
        with pytest.raises(MaterialisationError):
            forge.materialise(bp)

    def test_unknown_kind_rejected(self):
        forge = Forge()
        bp = forge.new_blueprint("x")
        with pytest.raises(BlueprintError):
            forge.instantiate(bp, "flux_capacitor", "f1")

    def test_port_direction_enforced(self):
        with pytest.raises(BlueprintError):
            Port("p", "event", "sideways")

    def test_custom_kind(self):
        forge = Forge()
        forge.register_kind("aggregator",
                            (Port("in", "event", "in"), Port("out", "event", "out")))
        assert "aggregator" in forge.available_kinds()
