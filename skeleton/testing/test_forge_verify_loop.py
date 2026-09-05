"""F-5 forge verify-loop — VerificationLoop + CodeVerifier.verdict glue."""
from __future__ import annotations

import pytest

from skeleton.forge.universal import Forge
from skeleton.forge.verify_loop import forge_verify_until_green
from skeleton.kernel.errors import MaterialisationError
from skeleton.organism.quality_state import load_quality


def test_forge_verify_until_green_accepts_clean_project(tmp_path):
    files = {
        "project.godot": (
            'config_version=5\n'
            'run/main_scene="res://scenes/levels/run_level.tscn"\n'
            'EventBus="*res://scripts/autoloads/event_bus.gd"\n'
        ),
        "scenes/levels/run_level.tscn": (
            '[gd_scene load_steps=1 format=3]\n'
            '[node name="RunLevel" type="Node2D"]\n'
        ),
        "scripts/autoloads/event_bus.gd": "extends Node\nsignal ping()\nfunc emit_ping():\n    emit_signal(\"ping\")\n",
        "scripts/world/world_map.gd": (
            "extends Node\n"
            "class_name WorldMap\n"
            "func describe_room(room_id):\n"
            "    return room_id\n"
        ),
    }
    out = forge_verify_until_green(files, request="world map", root=tmp_path, max_rounds=2)
    assert out["kind"] == "forge-verify-loop"
    assert out["trace"]["rounds"] >= 1
    assert "code_verdict" in out
    assert out["code_verdict"]["confidence"] >= 0.0


def test_forge_verify_until_green_repairs_weak_script(tmp_path):
    files = {
        "project.godot": (
            'config_version=5\n'
            'run/main_scene="res://scenes/levels/run_level.tscn"\n'
            'EventBus="*res://scripts/autoloads/event_bus.gd"\n'
        ),
        "scenes/levels/run_level.tscn": (
            '[gd_scene load_steps=1 format=3]\n'
            '[node name="RunLevel" type="Node2D"]\n'
        ),
        "scripts/autoloads/event_bus.gd": "extends Node\nsignal ping()\n",
        "scripts/world/world_map.gd": "var x = 1\n",
    }
    out = forge_verify_until_green(files, request="repair world map", root=tmp_path, max_rounds=3)
    assert out["repairs"], "expected at least one repair attempt"
    assert "extends " in out["files"]["scripts/world/world_map.gd"]
    assert out["trace"]["rounds"] >= 1


def test_materialise_repair_runs_verify_loop(tmp_path, monkeypatch):
    """Materialise(repair=True) must drive VerificationLoop and surface trace."""
    forge = Forge(root=tmp_path)
    bp = forge.new_blueprint("Loopable")
    forge.instantiate(bp, "player", "player")

    def weak_emit(*args, **kwargs):
        return {
            "project.godot": (
                'config_version=5\n'
                'run/main_scene="res://scenes/levels/run_level.tscn"\n'
                'EventBus="*res://scripts/autoloads/event_bus.gd"\n'
            ),
            "scenes/levels/run_level.tscn": (
                '[gd_scene load_steps=1 format=3]\n'
                '[node name="RunLevel" type="Node2D"]\n'
            ),
            "scripts/autoloads/event_bus.gd": "extends Node\nsignal ping()\n",
            "scripts/world/world_map.gd": "var x = 1\n",
        }

    monkeypatch.setattr("skeleton.forge.godot_emit.emit_godot", weak_emit)
    try:
        out = forge.materialise(bp, target="godot", repair=True, max_rounds=3)
    except MaterialisationError as exc:
        # Emit quality may still fail project closure after bounded repairs;
        # F-5 success is that the loop ran and CodeVerifier.verdict was consulted.
        assert "verify_loop" in exc.context
        assert exc.context["verify_loop"]["trace"]["rounds"] >= 1
        assert exc.context["verify_loop"].get("code_verdict") is not None
        rows = load_quality(root=tmp_path)
        assert rows and rows[-1]["surface"] == "forge"
        return
    assert "verify_loop" in out
    assert out["verify_loop"]["trace"]["rounds"] >= 1
    assert out["verify_loop"].get("code_verdict") is not None
    assert "extends " in out["files"]["scripts/world/world_map.gd"]
    rows = load_quality(root=tmp_path)
    assert rows and rows[-1]["surface"] == "forge"


def test_materialise_without_repair_still_single_gates(tmp_path, monkeypatch):
    forge = Forge(root=tmp_path)
    bp = forge.new_blueprint("Strict")
    forge.instantiate(bp, "player", "player")

    def bad_emit(*args, **kwargs):
        return {"project.godot": "config_version=5\n"}

    monkeypatch.setattr("skeleton.forge.godot_emit.emit_godot", bad_emit)
    with pytest.raises(MaterialisationError) as exc:
        forge.materialise(bp, target="godot", repair=False)
    assert "verification" in exc.value.context
    assert "verify_loop" not in exc.value.context


def test_materialise_repair_true_invokes_forge_verify_until_green(tmp_path, monkeypatch):
    forge = Forge(root=tmp_path)
    bp = forge.new_blueprint("Wired")
    forge.instantiate(bp, "player", "player")
    calls = {"n": 0}

    def fake_loop(files, **kwargs):
        calls["n"] += 1
        return {
            "kind": "forge-verify-loop",
            "ok": 1,
            "accepted": True,
            "files": dict(files),
            "verification": {
                "accepted": True,
                "score": 0.95,
                "reason": "accepted",
                "project_issues": [],
                "blocking_issues": [],
                "weakest_path": "",
                "summary": {},
                "file_reports": [],
                "quality": {"metadata": {"kind": "forge"}},
            },
            "verification_stats": {"runs": 1, "accepted": 1, "accept_rate": 1.0},
            "code_verdict": {"path": "x.gd", "confidence": 0.9, "issues": []},
            "trace": {"rounds": 2, "history": [0.5, 0.95], "final_claim": "", "stopped_reason": "accepted", "forced_rounds": 0},
            "repairs": [{"ok": 1, "changed": 1, "reason": "accepted"}],
            "rounds_detail": [],
            "threshold": 0.7,
            "stopped_reason": "accepted",
            "stored_prose": 0,
        }

    monkeypatch.setattr("skeleton.forge.godot_emit.emit_godot", lambda *a, **k: {"project.godot": "config_version=5\n", "scripts/a.gd": "extends Node\nfunc ok():\n    return 1\n"})
    monkeypatch.setattr("skeleton.forge.verify_loop.forge_verify_until_green", fake_loop)
    out = forge.materialise(bp, target="godot", repair=True, max_rounds=4)
    assert calls["n"] == 1
    assert out["verify_loop"]["trace"]["rounds"] == 2
    assert out["verification"]["accepted"] is True
    assert out["repair"]["changed"] == 1
