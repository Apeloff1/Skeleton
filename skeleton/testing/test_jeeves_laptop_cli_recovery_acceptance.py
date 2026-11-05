"""Source-only lighthouse acceptance across CLI save, restart and recovery.

No model, engine binary, Windows device or consumer readiness is inferred.
"""
from __future__ import annotations

import json
from pathlib import Path

from skeleton.jeeves.worlds.laptop_cli import run
from skeleton.jeeves.worlds.laptop_flow import LaptopFlow
from skeleton.jeeves.worlds.world_canon import canonical

SAMPLES = Path(__file__).resolve().parents[2] / "examples" / "jeeves"


def command(capsys, root, *args, expected=0):
    status = run(["--store", str(root), *args])
    output = json.loads(capsys.readouterr().out)
    assert status == expected, output
    assert output["ok"] is (expected == 0)
    return output


def reviewed_world(capsys, root):
    proposal = command(capsys, root, "propose", "--brief-file",
                       str(SAMPLES / "lighthouse_brief.json"))["result"]
    reviewed = command(
        capsys, root, "review", "--world-id", "lighthouse",
        "--expected-digest", proposal["source_digest"],
        "--operation-file", str(SAMPLES / "lighthouse_review.json"),
        "--review-note", "Explicit original lighthouse review for source custody.",
    )["result"]
    receipt = command(capsys, root, "compile", "--world-id", "lighthouse",
                      "--expected-digest", reviewed["source_digest"])["result"]
    assert command(capsys, root, "verify", "--world-id", "lighthouse")["result"] == receipt
    return reviewed, receipt


def test_cli_lighthouse_restarts_and_restores_without_overwrite(tmp_path, capsys):
    reviewed, receipt = reviewed_world(capsys, tmp_path)
    first = command(capsys, tmp_path, "session-create", "--world-id", "lighthouse",
                    "--slot", "original")["result"]
    second = command(
        capsys, tmp_path, "session-choose", "--world-id", "lighthouse",
        "--slot", "original", "--choice-id", "rescue",
        "--expected-session-digest", first["session_digest"],
    )["result"]
    export = command(capsys, tmp_path, "session-export", "--world-id",
                     "lighthouse", "--slot", "original")["result"]
    export_path = tmp_path / "portable.json"
    export_path.write_bytes(canonical(export))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    checked = command(capsys, tmp_path, "session-restore-check", "--world-id",
                      "lighthouse", "--export-file", str(export_path))["result"]
    assert checked["restorable"] is True
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == before

    # A fresh process/store object must not depend on cached review state.
    restarted = LaptopFlow(tmp_path)
    assert restarted.verify("lighthouse") == receipt
    assert restarted.inspect("lighthouse")["source_digest"] == reviewed["source_digest"]
    restored = command(capsys, tmp_path, "session-restore", "--world-id",
                       "lighthouse", "--slot", "recovered",
                       "--export-file", str(export_path))["result"]
    assert restored["session_digest"] == second["session_digest"]
    saved = tmp_path / "lighthouse.recovered.session.json"
    preserved = saved.read_bytes()
    failed = command(capsys, tmp_path, "session-restore", "--world-id",
                     "lighthouse", "--slot", "recovered",
                     "--export-file", str(export_path), expected=2)
    assert failed["error"] == "session_already_exists"
    assert failed["next_action"] == "select_an_unused_slot_without_overwriting"
    assert saved.read_bytes() == preserved

    acceptance = command(capsys, tmp_path, "acceptance", "--world-id",
                         "lighthouse", "--slot", "recovered")["result"]
    assert acceptance["source_digest"] == reviewed["source_digest"]
    assert acceptance["portable_roundtrip_verified"] is True
    assert acceptance["persisted_slot_verified"] is True
    assert acceptance["existing_session"]["session_digest"] == second["session_digest"]
    diagnostic = command(capsys, tmp_path, "diagnose", "--world-id",
                         "lighthouse", "--slot", "recovered")["result"]
    assert diagnostic["checks"]["acceptance"]["ok"] is True
    assert diagnostic["checks"]["session"]["ok"] is True
    assert diagnostic["next_action"] == "source_playable_handoff_ready_for_engine_validation"


def test_cli_corrupt_export_is_rejected_before_slot_creation(tmp_path, capsys):
    reviewed_world(capsys, tmp_path)
    command(capsys, tmp_path, "session-create", "--world-id", "lighthouse",
            "--slot", "original")
    export = command(capsys, tmp_path, "session-export", "--world-id",
                     "lighthouse", "--slot", "original")["result"]
    export["session"]["scene"] = "resolution"
    path = tmp_path / "tampered.json"
    path.write_bytes(canonical(export))
    before = sorted(p.name for p in tmp_path.iterdir())
    result = command(capsys, tmp_path, "session-restore-check", "--world-id",
                     "lighthouse", "--export-file", str(path), expected=2)
    assert result["error"] == "session_checksum_mismatch"
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    result = command(capsys, tmp_path, "session-restore", "--world-id",
                     "lighthouse", "--slot", "untrusted",
                     "--export-file", str(path), expected=2)
    assert result["error"] == "session_checksum_mismatch"
    assert not (tmp_path / "lighthouse.untrusted.session.json").exists()
