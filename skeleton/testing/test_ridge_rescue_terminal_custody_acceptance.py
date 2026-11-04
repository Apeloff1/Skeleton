"""Consumer terminal completion must produce replay-verifiable custody artifacts."""
from pathlib import Path

from skeleton.game.gameplay.ridge_rescue.consumer_acceptance import run_acceptance
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


def test_earned_ending_terminal_export_backup_and_audit(tmp_path: Path):
    root = tmp_path / "saves"
    result = run_acceptance(root)
    assert result["interactive_quit_restart_verified"] is True
    assert result["interactive_export_backup_verified"] is True
    assert result["portable_export_verified"] is True
    assert result["backup_restore_replay_verified"] is True
    assert result["exact_head_ci_certified"] is False
    assert result["windows_device_certified"] is False
    completed = SlotStore(root).load("interactive-acceptance")
    assert completed["status"] == "completed"
    assert completed["head"] == result["head"]
    assert SlotStore(root).audit("interactive-acceptance")["verified"] is True
