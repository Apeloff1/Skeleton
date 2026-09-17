from __future__ import annotations

import json

from skeleton.game.world_bundle import bundle
from skeleton.game.world_tick import play


def test_bundle_sealed() -> None:
    left = bundle(seed=8847291)
    right = bundle(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["extract_count"] == 1
    assert left["monte"] == 4
    assert left["arena_match"] is True
    assert left["arena_split"] is False
    assert left["sota_ready"] is False
    assert bundle(seed=3)["digest"] != left["digest"]


def test_world_still_extracts_once() -> None:
    card = play(seed=8847291, ticks=16)
    assert card["extract_count"] == 1
    assert card["path_len"] >= 2
    assert card["coil"] >= 1


def test_cli_bundle(capsys) -> None:
    from skeleton.__main__ import main

    assert main(["bundle", "--seed", "8847291"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["sota_ready"] is False
    assert payload["extract_count"] == 1
