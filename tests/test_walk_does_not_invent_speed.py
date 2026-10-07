"""A walk does not invent a player speed or a heat system."""

import pytest

from skeleton.forge.walk import _adj, _heat_cfg, _speed


def test_missing_speed_and_heat_are_refused() -> None:
    with pytest.raises(ValueError):
        _speed({})
    with pytest.raises(ValueError):
        _speed({"player": {"speed": 0}})
    assert _speed({"player": {"speed": 155}}) == 155
    with pytest.raises(ValueError):
        _heat_cfg({})
    cfg = _heat_cfg({"heat": {"max_heat": 10, "passive_cool": 0, "sprint_heat_per_sec": 0}})
    assert cfg == {"max": 10, "cool": 0, "sprint": 0}
    with pytest.raises(ValueError):
        _adj(
            {"rooms": [{"id": "a", "x": 0, "y": 0}], "doors": [{"from": "a", "to": "missing"}]},
            {"player": {"speed": 100}},
        )
