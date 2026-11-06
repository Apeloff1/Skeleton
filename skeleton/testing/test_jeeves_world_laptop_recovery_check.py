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


def test_malformed_diagnostic_stage_is_fail_closed(tmp_path, monkeypatch):
    from skeleton.jeeves.worlds.laptop_flow import LaptopFlow
    from skeleton.jeeves.worlds.laptop_recovery_check import inspect_recovery

    def corrupted(self, world_id, slot=None):
        return {
            "source_digest": "a" * 64,
            "checks": {"source": None, "review": {"ok": True},
                       "builder": {"ok": True}, "acceptance": {"ok": True}},
            "next_action": "inspect_source",
        }

    monkeypatch.setattr(LaptopFlow, "diagnose", corrupted)
    monkeypatch.setattr(LaptopFlow, "inspect",
                        lambda self, world_id: {"source_digest": "a" * 64})
    result = inspect_recovery(tmp_path, "lighthouse")
    assert result["source_handoff_verified"] is False
    assert result["checks"]["source"]["error"] == "laptop_recovery_stage_invalid"


def test_contradictory_success_with_error_fails_closed(tmp_path, monkeypatch):
    from skeleton.jeeves.worlds.laptop_flow import LaptopFlow

    ready(tmp_path)
    original = LaptopFlow.diagnose

    def contradictory(self, world_id, slot=None):
        report = original(self, world_id, slot)
        report["checks"]["builder"] = {"ok": True, "error": "builder_custody_mismatch"}
        return report

    monkeypatch.setattr(LaptopFlow, "diagnose", contradictory)
    result = inspect_recovery(tmp_path, "lighthouse")
    assert result["source_handoff_verified"] is False
    assert result["checks"]["builder"] == {
        "ok": False, "error": "laptop_recovery_stage_contradictory"
    }
    assert result["next_action"] == "inspect_canonical_custody_without_overwriting_artifacts"


def test_command_success_emits_one_canonical_newline_terminated_record(tmp_path, capsys):
    """Exercise the actual CLI success path, including byte framing."""
    _, _, reviewed, _ = ready(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    status = main([
        "--store", str(tmp_path), "--world-id", "lighthouse",
        "--expect-source-digest", reviewed["source_digest"],
    ])
    captured = capsys.readouterr()
    assert status == 0
    assert captured.err == ""
    assert captured.out.endswith("\n")
    assert captured.out.count("\n") == 1
    result = json.loads(captured.out)
    assert result["source_handoff_verified"] is True
    assert result["source_digest"] == reviewed["source_digest"]
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == before


def test_command_invalid_digest_emits_one_failure_record(tmp_path, capsys):
    status = main([
        "--store", str(tmp_path), "--world-id", "lighthouse",
        "--expect-source-digest", "not-a-sha256",
    ])
    captured = capsys.readouterr()
    assert status == 2
    assert captured.out.endswith("\n")
    assert captured.out.count("\n") == 1
    assert json.loads(captured.out)["error"] == "expected_source_digest_invalid"
