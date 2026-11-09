"""Bounded, genuinely stateful maze and RPG game-builder acceptance."""
from __future__ import annotations

from copy import deepcopy
import pytest

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    AdvancedRuntimeError, run_advanced_session, verify_advanced_session,
)


def test_maze_has_replayable_key_gated_level_completion():
    settings = {"width": 5, "height": 5, "levels": 1,
                "hazards": 0, "topology": "grid"}
    actions = ["south"] * 4 + ["east"] * 4
    receipt = run_advanced_session("maze", settings, actions, seed=4)
    assert receipt["validated_turn_count"] == 8
    assert receipt["state"]["finished"] is True
    assert receipt["state"]["completed_levels"] == 1
    assert receipt["state"]["has_key"] is True
    assert receipt["native_hardware_verified"] is False
    assert receipt["publication_certified"] is False
    assert verify_advanced_session(receipt, settings)
    assert run_advanced_session("maze", settings, actions, seed=4) == receipt
    forged = deepcopy(receipt)
    forged["state"]["has_key"] = False
    with pytest.raises(AdvancedRuntimeError):
        verify_advanced_session(forged, settings)


def test_maze_wall_inputs_cannot_mint_progress_or_finite_health():
    session = run_advanced_session(
        "maze", {"width": 5, "height": 5, "levels": 2, "hazards": 0},
        ["west", "north", "survey"], seed=0,
    )
    assert session["state"]["completed_levels"] == 0
    assert session["state"]["visits"] == 1
    assert session["state"]["health"] == 4
    assert session["state"]["position"] == [0, 0]
    assert verify_advanced_session(session, {"width": 5, "height": 5,
                                              "levels": 2, "hazards": 0})


def test_rpg_branching_affects_quest_outcome_and_replay_identity():
    settings = {"party_size": 4, "quest_depth": 1, "level_cap": 5}
    prefix = ["talk", "accept", "explore"]
    guild = run_advanced_session("rpg", settings, prefix + [
        "ally", "fight", "resolve",
    ])
    outlaw = run_advanced_session("rpg", settings, prefix + [
        "oppose", "fight", "resolve",
    ])
    assert guild["state"]["finished"] and outlaw["state"]["finished"]
    assert guild["state"]["reputation"]["guild"] == 1
    assert outlaw["state"]["reputation"]["outlaws"] == 1
    assert guild["state"]["reputation"]["settlers"] == 1
    assert outlaw["state"]["reputation"]["settlers"] == -1
    assert guild["digest"] != outlaw["digest"]
    assert guild["state"]["world_flags"] != outlaw["state"]["world_flags"]
    assert verify_advanced_session(guild, settings)
    assert verify_advanced_session(outlaw, settings)


def test_rpg_rejects_free_rewards_and_unapproved_scene_documents():
    for commands in (["resolve"], ["accept"], ["fight"],
                     ["explore"], ["buy_rations"] * 5):
        with pytest.raises(AdvancedRuntimeError):
            run_advanced_session("rpg", actions=commands)
    with pytest.raises(AdvancedRuntimeError, match="authored scene"):
        run_advanced_session("rpg", scene={"editor": "rpg"})
    with pytest.raises(AdvancedRuntimeError):
        run_advanced_session("maze", actions=["teleport"])


def test_editor_preview_uses_actual_bounded_maze_and_rpg_engines():
    from skeleton.ai.game_builder.system_editors import preview_editor
    for editor, settings, commands in (
        ("maze", {"width": 5, "height": 5}, ["south", "survey"]),
        ("rpg", {"party_size": 3}, ["talk", "accept"]),
    ):
        view = preview_editor(editor, settings, commands)
        assert view["status"] == "deterministic_prototype"
        assert view["simulation_executed"] is True
        assert view["native_hardware_verified"] is False
        assert view["publication_certified"] is False
        assert view["state"]["tick"] == len(commands)
        assert len(view["digest"]) == 64
        assert view == preview_editor(editor, settings, commands)
    with pytest.raises(AdvancedRuntimeError):
        preview_editor("rpg", actions=["resolve"])
