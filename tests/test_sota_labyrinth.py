from __future__ import annotations

import json

import pytest

from skeleton.game.diffusion import run as diffuse
from skeleton.game.dream_warp import session as dream
from skeleton.game.lab_sim import play
from skeleton.game.labyrinth import LabyrinthError, analyze, weave
from skeleton.game.locks import solve
from skeleton.game.los import LosError, bresenham, visible
from skeleton.game.layouts import room
from skeleton.game.stealth import detect


def test_weave_unique_extract_and_analysis() -> None:
    maze = weave(seed=8847291, rooms=8)
    report = analyze(maze)
    assert report["extracts"] == 1
    assert report["spawn_reaches_extract"] is True
    assert maze["cycles"] >= 0
    other = weave(seed=17, rooms=8)
    assert other["edges"] != maze["edges"] or other["nodes"] != maze["nodes"]
    with pytest.raises(LabyrinthError):
        weave(seed=1, rooms=2)


def test_locks_diffusion_los_stealth_dream() -> None:
    maze = weave(seed=8847291, rooms=8)
    opened = solve(maze)
    assert opened["opened"] is True
    field = diffuse(maze, ticks=8, inject_at="r0")
    assert field["every_frame"] is False
    assert field["peak"] >= 0
    layout = room(8847291, 1, "scavenge")
    ray = bresenham(0, 0, 3, 2)
    assert ray[0] == (0, 0) and ray[-1] == (3, 2)
    assert visible(layout, (0, 0), (1, 0)) in {True, False}
    with pytest.raises(LosError):
        visible(layout, (-1, 0), (1, 1))
    sight = detect(
        player_room="r1",
        stalker_room="r1",
        stalker_mood="chase",
        heat=14,
        seed=8847291,
        room_index=1,
    )
    assert sight["same_room"] is True
    night = dream(seed=8847291, rooms=8)
    assert night["snapped"] is True


def test_lab_sim_sealed() -> None:
    left = play(seed=8847291, rooms=8)
    right = play(seed=8847291, rooms=8)
    assert left["digest"] == right["digest"]
    assert left["extract_count"] == 1
    assert left["warp_count"] == 1
    assert left["sota_ready"] is False
    assert play(seed=3, rooms=8)["digest"] != left["digest"]


def test_cli_lab(capsys) -> None:
    from skeleton.__main__ import main

    assert main(["lab", "--seed", "8847291"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["sota_ready"] is False
    assert payload["extract_count"] == 1
