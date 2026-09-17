from __future__ import annotations

import json

from skeleton.game.influence import card as influence_card
from skeleton.game.inventory import add, empty
from skeleton.game.labyrinth import weave
from skeleton.game.predicates import gate, is_hot, require_never_extracted
from skeleton.game.world_events import run as event_run
from skeleton.game.world_tick import play


def test_world_tick_sealed() -> None:
    left = play(seed=8847291, ticks=16)
    right = play(seed=8847291, ticks=16)
    assert left["digest"] == right["digest"]
    assert left["extract_count"] == 1
    assert left["sota_ready"] is False
    assert play(seed=3, ticks=16)["digest"] != left["digest"]


def test_events_inventory_predicates_influence() -> None:
    ev = event_run("extract_hum", 8847291, 3)
    assert ev["final"]["done"] is True
    bag = add(empty(), "coil", 1)
    assert bag["coil"] == 1
    assert is_hot({"heat": 9}) is True
    require_never_extracted({"extracted": 0})
    assert gate({"heat": 9, "extracted": 0}, ["hot", "never_extracted"]) is True
    maze = weave(seed=8847291, rooms=8)
    extract = next(n["id"] for n in maze["nodes"] if n["kind"] == "extract")
    field = influence_card(maze, extract)
    assert field["goal"] == extract


def test_cli_world(capsys) -> None:
    from skeleton.__main__ import main

    assert main(["world", "--seed", "8847291"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["sota_ready"] is False
    assert payload["extract_count"] == 1
