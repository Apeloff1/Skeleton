"""The simulator does not invent a gun, one hit point, or a kill."""

import pytest

from skeleton.forge.sim import simulate_encounter


def _pack():
    return {
        "primary_dps": 10,
        "recipes": [{"damage": 10, "rpm": 60, "heat": 0}],
        "heat": {"max_heat": 100, "passive_cool": 7.5, "critical_ratio": 0.78},
        "session": {"collapse_max": 5},
    }


def test_missing_combat_numbers_do_not_become_a_kill() -> None:
    with pytest.raises(ValueError):
        simulate_encounter({}, {"id": "trash", "hp": 10})
    with pytest.raises(ValueError):
        simulate_encounter(_pack(), {"id": "trash"})
    slow = simulate_encounter(_pack(), {"id": "boss", "hp": 1000, "ttk_target": 100})
    assert slow.killed is False
    assert slow.collapsed is True
    killed = simulate_encounter(_pack(), {"id": "trash", "hp": 10, "ttk_target": 1})
    assert killed.killed is True
    assert killed.measured_ttk == pytest.approx(1.0)
