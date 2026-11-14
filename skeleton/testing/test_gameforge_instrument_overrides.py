"""Source-level game design instrument contracts (no live model/Godot required)."""
from __future__ import annotations

import math

import pytest

from skeleton.context.pipeline import apply_operator_axes, normalise_operator_axes
from skeleton.context.tensor import AXES, ContextTensor


def test_sparse_knob_override_preserves_base_era_and_remaining_axes():
    source = ContextTensor.from_era("cozy_wholesome")
    updated = apply_operator_axes(source, {"risk": 0.91, "tempo": 0.86})
    assert updated.era == source.era
    assert updated["risk"] == 0.91
    assert updated["tempo"] == 0.86
    assert all(updated[axis] == source[axis] for axis in AXES if axis not in {"risk", "tempo"})
    assert updated.fingerprint() != source.fingerprint()
    assert apply_operator_axes(source, None).fingerprint() == source.fingerprint()


def test_instrument_serialization_stable_in_canonical_axis_order():
    values = {"tempo": 0.05, "risk": 1}
    assert list(normalise_operator_axes(values)) == ["risk", "tempo"]
    assert normalise_operator_axes(values) == {"risk": 1.0, "tempo": 0.05}


@pytest.mark.parametrize("invalid", [
    [],
    {"unknown": 0.5},
    {"__proto__": 0.5},
    {"risk": True},
    {"risk": "0.4"},
    {"risk": -0.1},
    {"risk": 1.01},
    {"risk": math.nan},
    {"risk": math.inf},
    {axis: 0.4 for axis in AXES} | {"one_more": 0.2},
])
def test_rejects_unsafe_or_unknown_operator_controls(invalid):
    with pytest.raises(ValueError):
        normalise_operator_axes(invalid)
