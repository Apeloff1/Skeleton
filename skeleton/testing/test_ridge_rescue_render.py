"""Player-facing scene view is deterministic, bounded and never leaks hidden enemies."""
from pathlib import Path
import pytest
from skeleton.game.gameplay.ridge_rescue.schema import parse_world
from skeleton.game.gameplay.ridge_rescue.engine import initial_state
from skeleton.game.gameplay.ridge_rescue.render import render_map, legend

WORLD = parse_world((Path(__file__).resolve().parents[1] / "game/gameplay/ridge_rescue/cinder_ridge.json").read_bytes())

def test_render_visibility_and_player():
    state = initial_state(WORLD)
    limited = render_map(WORLD, state, radius=2)
    full = render_map(WORLD, state, reveal=True)
    assert "@" in limited
    assert "R" not in limited
    assert "R" in full
    assert "Credits 0" in full
    assert "civilian" in legend()

def test_bad_radius_rejected():
    with pytest.raises(ValueError):
        render_map(WORLD, initial_state(WORLD), radius=-1)
    with pytest.raises(ValueError):
        render_map(WORLD, initial_state(WORLD), radius=True)
