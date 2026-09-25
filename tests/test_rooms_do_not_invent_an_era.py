"""A room graph does not invent an era, a bias, or a boolean."""

import pytest

from skeleton.forge.world import generate_rooms


def _pack():
    return {
        "era": "soulslike",
        "session": {"room_count_min": 4, "room_count_max": 4},
    }


def test_missing_counts_and_string_flags_are_refused() -> None:
    with pytest.raises(ValueError):
        generate_rooms({})
    with pytest.raises(ValueError):
        generate_rooms(_pack(), plan={"room_bias": "plaza"})
    with pytest.raises(ValueError):
        generate_rooms(_pack(), plan={"extract_late": "false"})
    with pytest.raises(ValueError):
        generate_rooms(_pack(), plan={"enemy_mix": {"trash": True}})
    graph = generate_rooms(_pack(), seed="fixed")
    assert graph["seed"] == "fixed"
    assert graph["era"] == "soulslike"
    assert graph["extract_late"] is False
    assert graph["occupancy"]["enemy"] == 0
    assert graph["count"] == 4
