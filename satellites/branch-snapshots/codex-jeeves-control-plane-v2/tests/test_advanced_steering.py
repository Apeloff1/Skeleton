"""Tests for advanced operator steering.

Covers vector registration, activation, deactivation, composite
building, interpolation, and constraint enforcement.
"""
from __future__ import annotations

import pytest

from skeleton.organism.advanced_operator_steering import (
    AdvancedOperatorSteering,
    SteeringVector,
)


class TestSteeringVector:
    def test_vector_creation(self):
        vec = SteeringVector(name="test", dims=[1.0, 0.0, 0.0], strength=2.0)
        assert vec.name == "test"
        assert vec.strength == 2.0

    def test_normalize(self):
        vec = SteeringVector(name="test", dims=[3.0, 4.0], strength=1.0)
        norm = vec.normalize()
        # 3-4-5 triangle
        assert abs(norm.dims[0] - 0.6) < 0.001
        assert abs(norm.dims[1] - 0.8) < 0.001

    def test_scaled(self):
        vec = SteeringVector(name="test", dims=[1.0, 0.0], strength=1.0)
        scaled = vec.scaled(2.0)
        assert scaled.dims[0] == 2.0
        assert scaled.strength == 2.0

    def test_to_dict(self):
        vec = SteeringVector(name="test", dims=[1.0, 0.0], strength=1.0)
        d = vec.to_dict()
        assert d["name"] == "test"
        assert d["strength"] == 1.0


class TestAdvancedOperatorSteering:
    def test_register(self):
        steering = AdvancedOperatorSteering(dim=8)
        vec = steering.register("mood_dark", strength=1.5)
        assert vec.name == "mood_dark"
        assert vec.strength == 1.5
        assert len(vec.dims) == 8

    def test_register_with_dims(self):
        steering = AdvancedOperatorSteering(dim=4)
        vec = steering.register("custom", dims=[0.5, 0.5, 0.5, 0.5], strength=1.0)
        assert vec.dims == [0.5, 0.5, 0.5, 0.5]

    def test_activate_deactivate(self):
        steering = AdvancedOperatorSteering(dim=4)
        steering.register("a")
        steering.register("b")
        steering.activate("a", weight=0.7)
        steering.activate("b", weight=0.3)
        assert "a" in steering._active
        assert "b" in steering._active
        steering.deactivate("a")
        assert "a" not in steering._active

    def test_composite_single(self):
        steering = AdvancedOperatorSteering(dim=4)
        steering.register("a", dims=[1.0, 0.0, 0.0, 0.0])
        steering.activate("a", weight=1.0)
        comp = steering.composite_vector()
        assert abs(comp[0] - 1.0) < 0.001
        assert abs(comp[1]) < 0.001

    def test_composite_blend(self):
        steering = AdvancedOperatorSteering(dim=4)
        steering.register("a", dims=[1.0, 0.0, 0.0, 0.0])
        steering.register("b", dims=[0.0, 1.0, 0.0, 0.0])
        steering.activate("a", weight=0.5)
        steering.activate("b", weight=0.5)
        comp = steering.composite_vector()
        assert abs(comp[0] - 0.5) < 0.01
        assert abs(comp[1] - 0.5) < 0.01

    def test_interpolate(self):
        steering = AdvancedOperatorSteering(dim=4)
        steering.register("a", dims=[1.0, 0.0, 0.0, 0.0])
        steering.register("b", dims=[0.0, 1.0, 0.0, 0.0])
        mid = steering.interpolate("a", "b", 0.5)
        assert abs(mid[0] - 0.5) < 0.01
        assert abs(mid[1] - 0.5) < 0.01

    def test_constraint_enforcement(self):
        steering = AdvancedOperatorSteering(dim=64)
        steering.register("constrained")
        steering.set_constraint("constrained", "safety", 0.0, 0.5)
        steering.activate("constrained", weight=1.0)
        comp = steering.composite_vector()
        idx = hash("safety") % 64
        assert 0.0 <= comp[idx] <= 0.5

    def test_card(self):
        steering = AdvancedOperatorSteering(dim=8)
        steering.register("a")
        steering.activate("a")
        card = steering.card()
        assert card["kind"] == "advanced-operator-steering-card"
        assert card["dim"] == 8
        assert "a" in card["active_vectors"]

    def test_unknown_vector_raises(self):
        steering = AdvancedOperatorSteering(dim=4)
        with pytest.raises(KeyError):
            steering.activate("nonexistent")
