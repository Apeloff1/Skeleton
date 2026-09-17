from __future__ import annotations

import json

import pytest

from skeleton.game.arena import ArenaError, run_arena
from skeleton.game.conductor import STEPS, execute
from skeleton.game.critique import CritiqueError, critique, improve, monte_carlo
from skeleton.game.intent import IntentError, compile_intent
from skeleton.game.world_graph import WorldGraphError, place, walk


def test_critique_weakest_and_no_retune() -> None:
    card = critique({"fun": 0.9, "clarity": 0.2, "feasibility": 0.7, "originality": 0.8})
    assert card["weakest"] == "clarity"
    assert card["doctor"] == "clarity"
    assert card["stored_prose"] == 0
    left = monte_carlo(seed=8847291, samples=16)
    right = monte_carlo(seed=8847291, samples=16)
    assert left == right
    assert left["retune"] is False
    improved = improve({"fun": 0.4, "clarity": 0.5, "feasibility": 0.6, "originality": 0.7}, seed=3)
    assert improved["retune"] is False
    assert improved["doctor"] == "fun"
    with pytest.raises(CritiqueError):
        critique({"fun": 1.2})


def test_intent_pointers_no_prose() -> None:
    card = compile_intent(
        "NEXUS-EXTRACT heat sleep https://github.com/Apeloff1/Skeleton/issues/807 godot"
    )
    assert card["stored_prose"] == 0
    assert card["n"] >= 1
    assert "emit" in card["fields"]
    assert "loop" in card["fields"]
    clash = compile_intent("godot and unity extract #807")
    assert "emit-engine" in clash["conflicts"]
    with pytest.raises(IntentError):
        compile_intent("   ")


def test_world_graph_extract_once() -> None:
    graph = place(seed=8847291, rooms=5)
    assert "spawn" in graph["domains"]
    assert "extract" in graph["domains"]
    walked = walk(graph)
    assert walked["extract_count"] == walked["warp_count"] == 1
    assert walked["passed"] is True
    assert walk(place(seed=8847291, rooms=5)) == walked
    with pytest.raises(WorldGraphError):
        place(seed=1, rooms=1)


def test_conductor_seven_steps_and_law() -> None:
    left = execute(seed=8847291, vision="NEXUS-EXTRACT #807", forges=4)
    right = execute(seed=8847291, vision="NEXUS-EXTRACT #807", forges=4)
    assert left["sota_ready"] is False
    assert left["law"] == "batch_complete_is_not_sota"
    assert left["stored_prose"] == 0
    assert [card["step"] for card in left["steps"]] == list(STEPS)
    assert left["reference"]["citation"] == "#807"
    assert left["mass_trajectory"][-1] / left["mass_trajectory"][0] <= 1.1**4 + 1e-6
    assert left["ok"] is True
    assert json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def test_arena_eval_partial_never_ready() -> None:
    card = run_arena()
    assert card["evidence"] == "eval-partial"
    assert card["sota_ready"] is False
    assert card["extract_ok"] is True
    assert card["n"] == 4
    assert card["unique_digests"] == 4
    assert run_arena()["rows"][0]["digest"] == card["rows"][0]["digest"]
    with pytest.raises(ArenaError):
        run_arena([])


def test_cli_conductor_and_arena(capsys: pytest.CaptureFixture[str]) -> None:
    from skeleton.__main__ import main

    assert main(["conductor", "--seed", "8847291"]) == 0
    conductor = json.loads(capsys.readouterr().out)
    assert conductor["ok"] is True
    assert conductor["sota_ready"] is False
    assert conductor["steps"] == 7
    assert main(["arena"]) == 0
    arena = json.loads(capsys.readouterr().out)
    assert arena["ok"] is True
    assert arena["sota_ready"] is False
    assert arena["evidence"] == "eval-partial"
