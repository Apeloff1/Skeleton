"""Scripted playtest agent: taxonomy without a GPU or Godot binary."""
from __future__ import annotations

from skeleton.forge.game_builder import prove_and_repair
from skeleton.forge.playtest_agent import classify_godot_report, scripted_playtest

SHOOTER = {
    "player_hp": 100,
    "economy": {"starting_balance": 5, "sink_cost": 1},
    "encounters": [{"hp": 1, "player_damage": 1, "enemy_damage": 0, "loot": 1}],
    "longform": {"completed": True, "ending_id": "return"},
}


def test_scripted_frames_pass_softlock_and_timeout_without_godot():
    passed = scripted_playtest(SHOOTER, "top_down_shooter", frames=4)
    assert passed["taxonomy"] == "passed"
    assert passed["godot_ran"] is False
    assert passed["core_loop_ok"] is False
    assert passed["repair_codes"] == ["playtest_agent:passed"]
    assert [step["action"] for step in passed["inputs"]] == ["move", "aim", "fire", "salvage"]

    stuck = scripted_playtest(
        {"longform": {"completed": True, "ending_id": "return"}},
        "platformer",
        frames=4,
    )
    assert stuck["marker"] == "stuck"
    assert stuck["taxonomy"] == "softlock"
    assert stuck["repair_codes"] == ["playtest_agent:softlock"]

    short = scripted_playtest(SHOOTER, "top_down_shooter", frames=2)
    assert short["taxonomy"] == "timeout"
    assert short["marker"] == ""
    assert short["frames_run"] == 2


def test_godot_classifier_does_not_invent_a_boot():
    missing = classify_godot_report({"status": "unavailable", "passed": False, "reason": "missing-godot-binary", "binary": None})
    assert missing == {
        "godot_ran": False,
        "core_loop_ok": False,
        "degraded": True,
        "degraded_reason": "missing-godot-binary",
        "playtest_status": "unavailable",
    }
    pretended = classify_godot_report({"status": "passed", "passed": True, "binary": None, "steps": [{"log_tail": "CORE_LOOP_OK"}]})
    assert pretended["godot_ran"] is False
    assert pretended["core_loop_ok"] is False
    booted = classify_godot_report({
        "status": "passed",
        "passed": True,
        "binary": "/usr/bin/godot",
        "steps": [{"log_tail": "CORE_LOOP_OK genre=top_down_shooter marker=cleared:1:gold:5"}],
    })
    assert booted["godot_ran"] is True
    assert booted["core_loop_ok"] is True
    assert booted["degraded"] is False


def test_repair_loop_reads_playtest_taxonomy(monkeypatch):
    seen: dict[str, list[str]] = {}

    def capture(files, errors, spec, content, **kwargs):
        del spec, content, kwargs
        seen["errors"] = list(errors)
        return dict(files), []

    monkeypatch.setattr("skeleton.forge.gdscript_check.check_files", lambda files: [])
    monkeypatch.setattr("skeleton.forge.game_builder.read_and_repair", capture)
    proved = prove_and_repair(
        {"project.godot": "config_version=5\n"},
        {"genre": "platformer", "brief": "ledges"},
        {"longform": {"completed": True, "ending_id": "return"}},
        playtest_mode="require",
        max_rounds=2,
    )
    assert proved["playtest_agent"]["taxonomy"] == "softlock"
    assert "playtest_agent:softlock" in seen["errors"]
    assert proved["ok"] is False


def test_auto_without_godot_keeps_the_degraded_pass(monkeypatch):
    monkeypatch.setattr("skeleton.forge.gdscript_check.check_files", lambda files: [])
    monkeypatch.setattr(
        "skeleton.forge.game_builder.playtest",
        lambda *args, **kwargs: {
            "status": "unavailable",
            "passed": False,
            "reason": "missing-godot-binary",
            "binary": None,
            "errors": [],
            "steps": [],
        },
    )
    proved = prove_and_repair(
        {"project.godot": "config_version=5\n"},
        {"genre": "top_down_shooter", "brief": "ash"},
        SHOOTER,
        playtest_mode="auto",
    )
    assert proved["ok"] is True
    assert proved["playtest"]["status"] == "unavailable"
    assert proved["playtest"]["agent"]["taxonomy"] == "passed"
    assert proved["playtest"]["agent"]["godot_ran"] is False
    assert "CORE_LOOP_OK" not in str(proved["playtest"])
