"""Additional consumer acceptance contracts: real UI and replay equivalence."""
from __future__ import annotations

from skeleton.game.gameplay.ridge_rescue.consumer_acceptance import run_acceptance
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore
from skeleton.game.gameplay.ridge_rescue.acceptance import acceptance_actions
from skeleton.game.gameplay.ridge_rescue.campaign_acceptance import LAST_SIGNAL
from skeleton.game.gameplay.ridge_rescue.consumer_cli import play

def test_terminal_full_play_reaches_same_earned_ending(tmp_path):
    report = run_acceptance(tmp_path / "consumer")
    assert report["interactive_quit_restart_verified"]
    assert report["terminal_commands"] == report["actions"]
    assert report["terminal_frames"] >= report["actions"]
    assert report["portable_export_verified"]


def test_completed_terminal_save_is_stable(tmp_path):
    from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
    from skeleton.game.gameplay.ridge_rescue.campaign_acceptance import LAST_SIGNAL
    store = SlotStore(tmp_path / "saves")
    state = store.new("game")
    for action in acceptance_actions("protect") + LAST_SIGNAL:
        state = store.step("game", action, expected_head=state["head"])
    assert state["status"] == "completed"
    lines = []
    resumed = play(SlotStore(tmp_path / "saves"), "game",
                   read=lambda prompt: "q", write=lines.append)
    assert resumed["head"] == state["head"]
    assert any("Victory:" in line for line in lines)
