"""Player-visible action legality, authoring, route and delivery contracts."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_evacuation import (
    demo_actions, new_evacuation, normalize_evacuation,
    original_evacuation, simulate_evacuation,
)
from skeleton.game.gameplay.scene_evacuation_acceptance import accept_evacuation
from skeleton.game.gameplay.scene_evacuation_author import edit_evacuation
from skeleton.game.gameplay.scene_evacuation_board import (
    inspect_evacuation, legal_evacuation_actions,
)
from skeleton.game.gameplay.scene_evacuation_interactive import play_evacuation
from skeleton.game.gameplay.scene_evacuation_solver import solve_evacuation
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_board_enumerates_only_legal_source_bound_actions():
    source = original_evacuation()
    initial = new_evacuation(source)
    board = inspect_evacuation(initial)
    assert board["phase"] == "active"
    assert board["scene_id"] == "quay"
    assert {"kind": "rescue", "npc_id": "dock_apprentice"} in board["legal_actions"]
    assert {"kind": "rescue", "npc_id": "watch_keeper"} not in board["legal_actions"]
    assert {"kind": "protect"} not in board["legal_actions"]
    assert {"kind": "mission", "action": {"kind": "choose",
            "choice_id": "restore_lantern", "option_id": "help"}} in board["legal_actions"]
    assert board["receipt"] == dig({k: v for k, v in board.items() if k != "receipt"})


def test_board_earned_supply_and_terminal_legal_action_inventory():
    source, actions = original_evacuation(), demo_actions()
    checkpoint = simulate_evacuation(source, actions[:2])
    assert {"kind": "protect"} in legal_evacuation_actions(checkpoint)
    terminal = simulate_evacuation(source, actions)
    assert inspect_evacuation(terminal)["legal_actions"] == []


def test_author_digest_fence_and_preview_preserve_original_source():
    source = original_evacuation()
    before = copy.deepcopy(source)
    result = edit_evacuation(
        source, [{"npc_id": "watch_keeper", "changes": {"reward": 21}}],
        dig(normalize_evacuation(source)), preview_actions=demo_actions(),
    )
    assert source == before
    assert result["source"]["npcs"][1]["reward"] == 21
    assert result["preview"]["phase"] == "evacuated"
    assert result["preview"]["reward"] == 63
    assert result["source_digest"] != result["previous_source_digest"]
    with pytest.raises(SceneTravelError, match="digest mismatch"):
        edit_evacuation(source, [{"npc_id": "watch_keeper",
                                 "changes": {"reward": 21}}], "0" * 64)


def test_author_rejects_duplicate_invalid_and_unplayable_edits():
    source = original_evacuation()
    original_digest = dig(normalize_evacuation(source))
    with pytest.raises(SceneTravelError, match="duplicate"):
        edit_evacuation(source, [
            {"npc_id": "watch_keeper", "changes": {"reward": 21}},
            {"npc_id": "watch_keeper", "changes": {"reward": 22}},
        ], original_digest)
    with pytest.raises(SceneTravelError, match="invalid"):
        edit_evacuation(source, [
            {"npc_id": "watch_keeper", "changes": {"health": True}},
        ], original_digest)
    with pytest.raises(SceneTravelError):
        edit_evacuation(source, [
            {"npc_id": "watch_keeper", "changes": {"expires_at": 0}},
        ], original_digest, preview_actions=demo_actions())


def test_interactive_script_and_portable_game_acceptance():
    source, actions = original_evacuation(), demo_actions()
    played = play_evacuation(source, actions)
    assert played["phase"] == "evacuated"
    assert len(played["frames"]) == len(actions) + 1
    assert played["checkpoint"] == simulate_evacuation(source, actions)
    report = accept_evacuation(source, actions)
    assert report["phase"] == "evacuated"
    assert report["reward"] == 60
    assert report["checkpoints_verified"] == len(actions) + 1
    assert len(report["portable_checksum"]) == 64


def test_script_rejects_illegal_player_input_and_mismatched_checkpoint():
    source = original_evacuation()
    with pytest.raises(SceneTravelError, match="not legal"):
        play_evacuation(source, [{"kind": "rescue", "npc_id": "watch_keeper"}])
    other = copy.deepcopy(source)
    other["base_reward"] += 1
    with pytest.raises(SceneTravelError, match="source mismatch"):
        play_evacuation(other, [], checkpoint=new_evacuation(source))


def test_solver_returns_only_replay_proven_witness_and_bounded_inconclusive():
    source, actions = original_evacuation(), demo_actions()
    found = solve_evacuation(source, hint_actions=actions)
    assert found["status"] == "found"
    assert found["actions"] == actions
    assert found["state_digest"] == simulate_evacuation(source, actions)["state_digest"]
    bounded = solve_evacuation(source, max_nodes=1, max_depth=1)
    assert bounded["status"] == "inconclusive"
    assert bounded["expanded"] == 1


@pytest.mark.parametrize("nodes,depth", [(0, 10), (4097, 10), (10, 0),
                                          (10, 33), (True, 10)])
def test_solver_rejects_unbounded_or_invalid_budgets(nodes, depth):
    with pytest.raises(SceneTravelError, match="budget"):
        solve_evacuation(original_evacuation(), max_nodes=nodes, max_depth=depth)


def test_acceptance_rejects_partial_outcome_without_false_certification():
    source = original_evacuation()
    source["npcs"][0]["health"] = 1
    actions = [action for action in demo_actions() if action["kind"] != "protect"]
    with pytest.raises(SceneTravelError, match="earned victory"):
        accept_evacuation(source, actions)


def test_solver_caps_generated_states_as_well_as_expansions():
    report = solve_evacuation(original_evacuation(), max_nodes=4, max_depth=8)
    assert report["status"] == "inconclusive"
    assert 1 <= report["generated"] <= 4
    assert 1 <= report["expanded"] <= 4


def test_live_player_input_uses_bounded_read_and_preserves_checkpoint(monkeypatch):
    import io
    from skeleton.game.gameplay.scene_evacuation_interactive import _live

    reader = io.StringIO("quit\n")
    monkeypatch.setattr("sys.stdin", reader)
    checkpoint = _live(original_evacuation())
    assert checkpoint["state"]["phase"] == "active"
    assert checkpoint["state"]["tick"] == 0


def test_live_player_rejects_oversized_line_before_json_parse(monkeypatch):
    import io
    from skeleton.game.gameplay.scene_evacuation import MAX_BYTES
    from skeleton.game.gameplay.scene_evacuation_interactive import _live

    monkeypatch.setattr("sys.stdin", io.StringIO(" " * (MAX_BYTES + 2) + "\n"))
    with pytest.raises(SceneTravelError, match="byte budget"):
        _live(original_evacuation())
