"""An emitter does not invent an era, a speed, or a heat value of zero."""

import pytest

from skeleton.forge.godot_emit import emit_godot


def _pack():
    return {
        "era": "arcade_golden_age",
        "player": {"speed": 160, "sprint_multiplier": 1},
        "heat": {
            "max_heat": 1,
            "passive_cool": 99,
            "critical_ratio": 1,
            "kinetic_heat": 0,
            "energy_heat": 0,
            "sprint_heat_per_sec": 0,
        },
        "session": {"collapse_max": 90},
    }


def test_a_blank_pack_is_not_a_default_game() -> None:
    with pytest.raises(ValueError):
        emit_godot({})
    missing = _pack()
    del missing["heat"]["kinetic_heat"]
    with pytest.raises(ValueError):
        emit_godot(missing)
    files = emit_godot(_pack(), title="ARCADE")
    assert "project.godot" in files
    assert "var amt := 0.0" in files["scripts/autoloads/heat_system.gd"]
    assert "speed: float = 160.0" in files["scripts/player/player_controller.gd"]
