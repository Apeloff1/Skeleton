"""Deterministic source-bound checks for the read-only laptop recovery command."""
from __future__ import annotations

import json

from skeleton.jeeves.worlds.laptop_recovery_check import inspect_recovery, main
from skeleton.testing.test_jeeves_world_laptop_flow import ready


def test_absent_world_is_not_reported_ready(tmp_path):
    result = inspect_recovery(tmp_path, "lighthouse")
    assert result["source_handoff_verified"] is False
    assert result["checks"]["source"]["error"] == "not_found"
    assert not list(tmp_path.glob("*.json"))


def test_reviewed_handoff_is_verified_without_player_mutation(tmp_path):
    flow, _, reviewed, receipt = ready(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    result = inspect_recovery(tmp_path, "lighthouse")
    assert result["source_handoff_verified"] is True
    assert result["source_digest"] == reviewed["source_digest"]
    assert result["checks"]["acceptance"]["ok"] is True
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == before


def test_corrupt_handoff_fails_closed_and_preserves_save(tmp_path):
    flow, _, _, receipt = ready(tmp_path)
    flow.create_session("lighthouse", "player")
    slot = tmp_path / "lighthouse.player.session.json"
    before = slot.read_bytes()
    builder = tmp_path / receipt["builder_file"]
    builder.write_bytes(builder.read_bytes() + b"\n")
    result = inspect_recovery(tmp_path, "lighthouse", "player")
    assert result["source_handoff_verified"] is False
    assert result["checks"]["builder"]["error"] == "laptop_builder_mismatch"
    assert slot.read_bytes() == before


def test_player_slot_required_when_requested(tmp_path):
    ready(tmp_path)
    result = inspect_recovery(tmp_path, "lighthouse", "missing")
    assert result["source_handoff_verified"] is False
    assert result["checks"]["session"]["ok"] is False


def test_command_reports_typed_failure_without_traceback(tmp_path, capsys):
    assert main(["--store", str(tmp_path), "--world-id", "lighthouse"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["source_handoff_verified"] is False
    assert output["next_action"]
