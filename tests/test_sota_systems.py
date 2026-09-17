from __future__ import annotations

import json

import pytest

from skeleton.game.combat_resolve import CombatResolveError, party_resolve, resolve
from skeleton.game.craft_graph import CraftGraphError, cycles, default_book, plan
from skeleton.game.economy_sim import EconomySimError, run as econ
from skeleton.game.heat_model import HeatModelError, run as heat_run
from skeleton.game.layouts import campus
from skeleton.game.pathfind import PathfindError, bfs, extract_route
from skeleton.game.quest_engine import nexus_book, run as quests
from skeleton.game.sim_loop import play
from skeleton.game.stalker import hunt
from skeleton.game.world_graph import place
from skeleton.game.godot_scripts import pack


def test_pathfind_extract_unique() -> None:
    graph = place(seed=8847291, rooms=5)
    route = extract_route(graph)
    assert route["warp_count"] == 1
    assert route["path"][0] == "r0"
    assert route["path"][-1].startswith("r")
    with pytest.raises(PathfindError):
        bfs(graph, "r0", "missing")


def test_craft_and_economy() -> None:
    built = plan(default_book(), "coil", {"scrap": 2})
    assert built["order"] == ["r_coil"]
    assert cycles([{"id": "a", "in": ("b",), "out": "a"}, {"id": "b", "in": ("a",), "out": "b"}])
    with pytest.raises(CraftGraphError):
        plan(
            [{"id": "a", "in": ("b",), "out": "a"}, {"id": "b", "in": ("a",), "out": "b"}],
            "a",
            {},
        )
    bag = econ([{"verb": "scavenge"}, {"verb": "scavenge"}, {"verb": "trade", "give": "scrap", "take": "parts"}])
    assert bag["bag"]["parts"] >= 1
    with pytest.raises(EconomySimError):
        econ([{"verb": "nope"}])


def test_combat_stalker_quests_heat_layouts_godot() -> None:
    fight = resolve(seed=3, rounds=6)
    assert fight["winner"] in {"player", "enemy", "draw"}
    party = party_resolve(3, [{"hp": 20}, {"hp": 20}])
    assert party["party"] == 2
    with pytest.raises(CombatResolveError):
        resolve(seed=1, rounds=0)
    graph = place(seed=8847291, rooms=5)
    hunted = hunt(graph, seed=8847291, ticks=10)
    assert hunted["ticks"] == 10
    book = quests(nexus_book(), ["heat", "heat", "heat", "extract", "craft", "bait"])
    assert book["done"] == 4
    model = heat_run(["heat", "heat", "extract", "sleep"])
    assert model["every_frame"] is False
    with pytest.raises(HeatModelError):
        heat_run(["dream"])
    space = campus(7, ["spawn", "heat", "extract"])
    assert space["n"] == 3
    scripts = pack(8847291)
    assert "player.gd" in scripts["files"]
    assert "func try_extract" in scripts["contents"]["player.gd"]
    assert scripts["godot_binary"] == 0


def test_sim_loop_sealed() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["sota_ready"] is False
    assert left["warp_count"] == 1
    assert play(seed=9)["digest"] != left["digest"]


def test_cli_sim(capsys) -> None:
    from skeleton.__main__ import main

    assert main(["sim", "--seed", "8847291"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["sota_ready"] is False
