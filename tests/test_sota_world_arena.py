from __future__ import annotations

import json

from skeleton.game.craft_inv import kit
from skeleton.game.floor_path import route
from skeleton.game.world_arena import compare, monte


def test_arena_match_and_split() -> None:
    same = compare(seed_a=8847291, seed_b=8847291, ticks=16)
    assert same["match"] is True
    split = compare(seed_a=8847291, seed_b=17, ticks=16)
    assert split["match"] is False
    assert same["extract_a"] == 1


def test_monte_four_unique() -> None:
    card = monte(seed=8847291, n=4, ticks=16)
    assert card["unique_digests"] == 4
    assert card["extracts"] == [1, 1, 1, 1]


def test_floor_path_and_craft() -> None:
    path = route(seed=8847291)
    assert path["spawn"].startswith("f0")
    assert path["extract"].startswith("f3")
    assert path["len"] >= 2
    bag = kit(8847291)
    assert bag["slots"]["coil"] >= 1


def test_cli_arena(capsys) -> None:
    from skeleton.__main__ import main

    assert main(["arena", "--seed", "8847291"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["match"] is True
    assert payload["sota_ready"] is False
