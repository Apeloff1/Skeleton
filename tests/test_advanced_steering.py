"""Tests for advanced operator steering."""
from __future__ import annotations

import pytest

from skeleton.organism.advanced_operator_steering import AdvancedOperatorSteering, SteeringVector


class TestSteeringVector:
    def test_normalize(self):
        v = SteeringVector(name="test", dims=[3.0, 4.0], strength=1.0)
        n = v.normalize()
        # 3-4-5 triangle, normalized should be [0.6, 0.8]
        assert abs(n.dims[0] - 0.6) < 1e-6
        assert abs(n.dims[1] - 0.8) < 1e-6
        assert n.strength == 1.0

    def test_scaled(self):
        v = SteeringVector(name="test", dims=[1.0, 0.0], strength=1.0)
        s = v.scaled(2.0)
        assert s.dims == [2.0, 0.0]
        assert s.strength == 2.0

    def test_to_dict(self):
        v = SteeringVector(name="test", dims=[1.0, 0.0], strength=1.0, constraints={"x": (0.0, 1.0)})
        d = v.to_dict()
        assert d["name"] == "test"
        assert d["constraints"] == {"x": (0.0, 1.0)}


class TestAdvancedOperatorSteering:
    def test_register(self):
        steering = AdvancedOperatorSteering(dim=4)
        v = steering.register("mood", dims=[1.0, 0.0, 0.0, 0.0])
        assert v.name == "mood"
        assert "mood" in steering._vectors

    def test_register_random(self):
        steering = AdvancedOperatorSteering(dim=4)
        v = steering.register("random")
        assert v.name == "random"
        assert len(v.dims) == 4
        # Should be unit vector
        import math
        norm = math.sqrt(sum(d * d for d in v.dims))
        assert abs(norm - 1.0) < 1e-6

    def test_activate_deactivate(self):
        steering = AdvancedOperatorSteering(dim=2)
        steering.register("a", dims=[1.0, 0.0])
        steering.activate("a", weight=1.0)
        assert "a" in steering._active
        steering.deactivate("a")
        assert "a" not in steering._active

    def test_activate_unknown_raises(self):
        steering = AdvancedOperatorSteering(dim=2)
        with pytest.raises(KeyError):
            steering.activate("unknown")

    def test_composite_single(self):
        steering = AdvancedOperatorSteering(dim=2)
        steering.register("a", dims=[1.0, 0.0])
        steering.activate("a")
        composite = steering.composite_vector()
        assert abs(composite[0] - 1.0) < 1e-6
        assert abs(composite[1] - 0.0) < 1e-6

    def test_composite_blend(self):
        steering = AdvancedOperatorSteering(dim=2)
        steering.register("a", dims=[1.0, 0.0])
        steering.register("b", dims=[0.0, 1.0])
        steering.activate("a", weight=1.0)
        steering.activate("b", weight=1.0)
        composite = steering.composite_vector()
        # Equal blend of [1,0] and [0,1] -> [0.5, 0.5]
        assert abs(composite[0] - 0.5) < 1e-6
        assert abs(composite[1] - 0.5) < 1e-6

    def test_composite_constraint(self):
        steering = AdvancedOperatorSteering(dim=4)
        steering.register("a", dims=[1.0, 0.0, 0.0, 0.0])
        steering.set_constraint("a", "x", 0.0, 0.5)
        steering.activate("a")
        composite = steering.composite_vector()
        idx = hash("x") % 4
        assert composite[idx] <= 0.5

    def test_interpolate(self):
        steering = AdvancedOperatorSteering(dim=2)
        steering.register("a", dims=[1.0, 0.0])
        steering.register("b", dims=[0.0, 1.0])
        result = steering.interpolate("a", "b", 0.5)
        assert abs(result[0] - 0.5) < 1e-6
        assert abs(result[1] - 0.5) < 1e-6

    def test_interpolate_unknown_raises(self):
        steering = AdvancedOperatorSteering(dim=2)
        with pytest.raises(KeyError):
            steering.interpolate("a", "b", 0.5)

    def test_card(self):
        steering = AdvancedOperatorSteering(dim=4)
        steering.register("a", dims=[1.0, 0.0, 0.0, 0.0])
        steering.activate("a", weight=0.8)
        card = steering.card()
        assert card["kind"] == "advanced-operator-steering-card"
        assert card["dim"] == 4
        assert "a" in card["active_vectors"]
        assert card["blend_weights"]["a"] == 0.8
