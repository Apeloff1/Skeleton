"""Game-logic repair tests."""
from __future__ import annotations

from skeleton.intelligence.game_logic_repair import attempt_game_logic_repair
from skeleton.organism.quality_state import latest_repair
from skeleton.pipelines.game_logic import GameLogicPipeline


def test_attempt_game_logic_repair_clamps_and_fills(tmp_path):
    out = attempt_game_logic_repair(
        {
            "title": "Broken",
            "combat": {"base_values": {"health": -10, "attack": 5}, "damage_formula": ""},
            "economy": {"currency": "", "starting_balance": -5, "taps": [], "sinks": []},
            "progression": {"curve": "", "max_level": 0, "base_xp": 100},
        },
        description="broken arena",
        root=tmp_path,
    )
    assert out["changed"] == 1
    assert out["spec"]["economy"]["currency"]
    assert out["spec"]["progression"]["max_level"] >= 1
    assert latest_repair(root=tmp_path, surface="game_logic")["kind"] == "repair"


def test_game_logic_pipeline_can_repair_once(tmp_path):
    pipe = GameLogicPipeline(root=tmp_path)
    spec = pipe.run("arena combat", title="Arena", repair=True)
    payload = spec.to_dict()
    assert "quality" in payload
