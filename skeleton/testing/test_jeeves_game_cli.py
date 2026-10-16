"""Jeeves and developer CLI share the same governed GameForge workspace."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from skeleton.developer.game_cli import run_game_cli
from skeleton.developer.jeeves_game_cli import run_jeeves_game_cli
from skeleton.forge.projector import write_project


def project(tmp_path: Path) -> Path:
    outcome = run_game_cli(["init", "jeeves-lab", "--dir", str(tmp_path),
                            "--vision", "An original branching RPG"])
    assert outcome["ok"], outcome
    return tmp_path / "jeeves-lab"


def test_jeeves_plan_uses_real_canonical_builder(tmp_path):
    root = project(tmp_path)
    first = run_jeeves_game_cli(["plan"], root)
    second = run_game_cli(["jeeves", "plan", "--project", str(root)])
    assert first["ok"] and second["ok"]
    assert first["plan_sha256"] == second["plan_sha256"]
    assert first["plan"]["era"] == "extraction_now"
    assert first["plan"]["seed"]
    assert first["model_inference"] is False
    assert first["checkpoint_verified"] is False


def test_jeeves_audit_never_fabricates_runtime_playthrough(tmp_path, monkeypatch):
    root = project(tmp_path)
    monkeypatch.setattr("skeleton.forge.playtest.resolve_binary",
                        lambda: (None, "missing-godot-binary", False))
    status = run_game_cli(["jeeves", "audit", "--project", str(root)])
    assert status["ok"] is False
    assert status["production_qualified"] is False
    assert "emitted_source_integrity" in status["blocking"]
    assert "godot_binary" in status["blocking"]
    assert next(x for x in status["checks"] if x["name"] == "headless_playthrough")["ok"] is False


def test_verified_source_is_shared_between_jeeves_and_game_cli(tmp_path, monkeypatch):
    root = project(tmp_path)
    write_project(root / "build" / "godot", {
        "project.godot": "config_version=5\n",
        "main.tscn": '[gd_scene format=3]\n[node name="Main" type="Node"]\n',
    })
    monkeypatch.setattr("skeleton.forge.playtest.resolve_binary",
                        lambda: ("/installed/godot", "test", False))
    audit = run_game_cli(["jeeves", "audit", "--project", str(root)])
    source = run_game_cli(["verify", "--project", str(root)])
    assert audit["ready_for_source_review"] is True
    assert audit["source_sha256"] == source["source_manifest"]["sha256"]
    assert audit["production_qualified"] is False
    assert run_game_cli(["jeeves", "next", "--project", str(root)])["recommendations"]
    handoff = run_game_cli(["jeeves", "handoff", "--project", str(root)])
    assert handoff["source_sha256"] == source["source_manifest"]["sha256"]


def test_jeeves_context_tracks_real_notes_without_writing(tmp_path):
    root = project(tmp_path)
    note = root / "design" / "canon.md"
    note.write_text("The protagonist has one consistent origin.", encoding="utf-8")
    context = run_game_cli(["jeeves", "context", "--project", str(root)])
    assert context["ok"] is True
    assert context["notes"][0]["path"] == "design/canon.md"
    assert context["notes"][0]["sha256"] == hashlib.sha256(note.read_bytes()).hexdigest()
    assert not list(root.rglob("*jeeves*.json"))


def test_jeeves_context_rejects_symlink_notes(tmp_path):
    root = project(tmp_path)
    (root / "design" / "outside.md").symlink_to(root / "skeleton.game.json")
    result = run_game_cli(["jeeves", "context", "--project", str(root)])
    assert result["ok"] is False
    assert "symlink" in result["error"]


def test_jeeves_cli_returns_nonzero_for_failed_audit(tmp_path, capsys, monkeypatch):
    from skeleton.developer.cli import main
    root = project(tmp_path)
    monkeypatch.setattr("skeleton.forge.playtest.resolve_binary",
                        lambda: (None, "missing", False))
    assert main(["game", "jeeves", "audit", "--project", str(root)]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False
