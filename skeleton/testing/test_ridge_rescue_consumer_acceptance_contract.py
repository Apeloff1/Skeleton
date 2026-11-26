"""End-to-end consumer acceptance on canonical runtime, with durable restart custody.

These tests are host-neutral. They do not qualify a Windows installer or device.
"""
from __future__ import annotations

from skeleton.game.gameplay.ridge_rescue.consumer_acceptance import (
    CONTRACT, run_acceptance,
)
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


def test_interactive_game_earns_ending_and_survives_cold_restart(tmp_path):
    root = tmp_path / "consumer-saves"
    report = run_acceptance(root)
    assert report["schema"] == CONTRACT
    assert report["status"] == "verified-in-process"
    assert report["chapters"] == 2
    assert report["actions"] > 0
    assert report["saved_revision"] == report["actions"]
    assert report["restart_count"] == report["actions"]
    assert report["terminal_commands"] == report["actions"]
    assert report["terminal_frames"] >= report["actions"]
    assert report["interactive_quit_restart_verified"] is True
    assert report["interactive_export_backup_verified"] is True
    assert report["portable_export_verified"] is True
    assert report["backup_restore_replay_verified"] is True
    assert report["windows_device_certified"] is False
    assert report["exact_head_ci_certified"] is False
    assert report["release_certified"] is False

    # A new store instance must replay the same earned ending and audit ledger.
    reopened = SlotStore(root).load("consumer-acceptance")
    audit = SlotStore(root).audit("consumer-acceptance")
    recovered = SlotStore(root).load("consumer-recovered")
    interactive = SlotStore(root).load("interactive-acceptance")
    terminal_backup = SlotStore(root).load("terminal-backup-recovered")
    for session in (reopened, recovered, interactive, terminal_backup):
        assert session["status"] == "completed"
        assert session["head"] == report["head"]
        assert session["revision"] == report["actions"]
    assert audit["verified"] is True
    assert audit["audit_entries"] == report["actions"]


def test_separate_acceptance_runs_are_deterministic(tmp_path):
    first = run_acceptance(tmp_path / "first")
    second = run_acceptance(tmp_path / "second")
    assert first["head"] == second["head"]
    assert first["actions"] == second["actions"]
    assert first["terminal_commands"] == second["terminal_commands"]
    assert first["terminal_frames"] == second["terminal_frames"]
