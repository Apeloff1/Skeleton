"""Forge verification gate tests.

Covers project acceptance/rejection over emitted Godot file sets and the
materialisation chokepoint that now enforces the verifier.
"""

from __future__ import annotations

import pytest

from skeleton.intelligence.forge_verifier import ForgeVerifier
from skeleton.kernel.errors import MaterialisationError
from skeleton.organism.quality_state import latest_failure, load_quality


def _bp(tmp_path=None):
    from skeleton.forge.universal import Forge

    forge = Forge(root=tmp_path)
    bp = forge.new_blueprint("VerifierGate")
    forge.instantiate(bp, "player", "player")
    return forge, bp


def test_forge_verifier_accepts_emitted_project():
    from skeleton.forge.godot_emit import emit_godot
    from skeleton.forge.eras import compile_era

    files = emit_godot(compile_era("extraction_now"), title="VerifierGate")
    report = ForgeVerifier().verify(files, request="VerifierGate")
    assert report.accepted
    assert report.score >= 0.7
    assert report.reason == "accepted"
    assert report.quality.accepted is True
    assert report.quality.metadata["kind"] == "forge"
    assert not report.project_issues
    assert report.file_reports
    assert report.summary["files_checked"] == len(report.file_reports)
    assert report.file_reports == tuple(sorted(report.file_reports, key=lambda r: (r.score, r.path)))


def test_forge_verifier_rejects_missing_required_file():
    from skeleton.forge.godot_emit import emit_godot
    from skeleton.forge.eras import compile_era

    files = emit_godot(compile_era("extraction_now"), title="VerifierGate")
    files.pop("project.godot")
    report = ForgeVerifier().verify(files)
    assert not report.accepted
    assert report.reason == "project_closure"
    assert report.quality.reason == "project_closure"
    assert any("missing project.godot" in issue for issue in report.project_issues)


def test_forge_verifier_rejects_bad_gdscript():
    files = {
        "project.godot": 'config_version=5\nrun/main_scene="res://scenes/levels/run_level.tscn"\n',
        "scenes/levels/run_level.tscn": '[gd_scene load_steps=1 format=3]\n[node name="RunLevel" type="Node2D"]\n',
        "scripts/autoloads/heat_system.gd": 'extends Node\nfunc bad(:\n    eval(user_input\n',
        "scripts/autoloads/jeeves.gd": 'extends Node\nfunc _process(_delta):\n    pass\n',
        "scripts/player/player_controller.gd": 'extends Node\nfunc _physics_process(_delta):\n    HeatSystem.add_sprint_heat(0.1)\n    move_and_slide()\n',
        "scripts/combat/enemy.gd": 'extends Node\nfunc take_damage(amount):\n    pass\n',
        "scripts/world/world_map.gd": 'extends Node\nfunc room_name():\n    return "r00"\n',
        "scripts/world/door.gd": 'extends Node\nfunc open():\n    pass\n',
        "scripts/autoloads/input_bind.gd": 'extends Node\nconst KEY_A = 65\nfunc _ready():\n    pass\n',
        "scenes/door.tscn": '[gd_scene load_steps=1 format=3]\n[node name="Door" type="Node2D"]\n',
        "data/rooms.json": '{}',
        "data/hardware.json": '{}',
        "scenes/player.tscn": '[gd_scene load_steps=1 format=3]\n[node name="Player" type="Node2D"]\n[node name="Cam" type="Camera2D" parent="."]\n',
        "scripts/autoloads/game_state.gd": 'extends Node\nfunc enter_room(rid):\n    pass\n',
    }
    report = ForgeVerifier().verify(files)
    assert not report.accepted
    assert any(r.path.endswith("heat_system.gd") and r.score < 0.7 for r in report.file_reports)
    assert any("unsafe" in issue or "unbalanced" in issue for issue in report.blocking_issues)
    assert any(i.path.endswith("heat_system.gd") and i.severity == "hard" for i in report.quality.issues)


def test_gdscript_verifier_accepts_func_without_python_def():
    report = ForgeVerifier()._verify_gdscript(
        "scripts/world/door.gd",
        'extends Node\nfunc open():\n    return true\n',
        request="door"
    )
    assert report.score >= 0.7
    assert "no func definition" not in report.issues
    assert report.subscores["structure"] >= 0.8


def test_gdscript_verifier_penalizes_missing_extends():
    report = ForgeVerifier()._verify_gdscript(
        "scripts/world/door.gd",
        'func open():\n    return true\n',
        request="door"
    )
    assert report.score < 0.7
    assert "missing extends" in report.soft_issues


def test_gdscript_verifier_flags_world_map_role_gap():
    report = ForgeVerifier()._verify_gdscript(
        "scripts/world/world_map.gd",
        'extends Node\nfunc tick():\n    return 1\n',
        request="world map"
    )
    assert "world map misses room or door semantics" in report.soft_issues


def test_verifier_stats_track_runs_and_acceptance():
    verifier = ForgeVerifier()
    verifier.verify({
        "project.godot": 'config_version=5\nrun/main_scene="res://scenes/levels/run_level.tscn"\n',
        "scenes/levels/run_level.tscn": '[gd_scene load_steps=1 format=3]\n[ext_resource type="PackedScene" path="res://scenes/player.tscn" id="3"]\n[ext_resource type="PackedScene" path="res://scenes/door.tscn" id="7"]\n[node name="RunLevel" type="Node2D"]\n[node name="Room_r00" type="Node2D" parent="."]\n[node name="Player" parent="." instance=ExtResource("3")]\n[node name="Door" parent="." instance=ExtResource("7")]\n',
        "scripts/autoloads/heat_system.gd": 'extends Node\nvar current_heat := 0.0\nsignal heat_critical\nfunc reset():\n    current_heat = 0.0\n',
        "scripts/autoloads/jeeves.gd": 'extends Node\nfunc _process(_delta):\n    pass\n',
        "scripts/player/player_controller.gd": 'extends Node\nfunc _physics_process(_delta):\n    HeatSystem.add_sprint_heat(0.1)\n    move_and_slide()\n',
        "scripts/combat/enemy.gd": 'extends Node\nfunc take_damage(amount):\n    pass\n',
        "scripts/world/world_map.gd": 'extends Node\nfunc room_name():\n    return "r00"\n',
        "scripts/world/door.gd": 'extends Node\nfunc open():\n    pass\n',
        "scripts/autoloads/input_bind.gd": 'extends Node\nconst KEY_A = 65\nfunc _ready():\n    pass\n',
        "scenes/door.tscn": '[gd_scene load_steps=1 format=3]\n[node name="Door" type="Node2D"]\n',
        "data/rooms.json": '{}',
        "data/hardware.json": '{}',
        "scenes/player.tscn": '[gd_scene load_steps=1 format=3]\n[node name="Player" type="Node2D"]\n[node name="Cam" type="Camera2D" parent="."]\n',
        "scripts/autoloads/game_state.gd": 'extends Node\nfunc enter_room(rid):\n    pass\n',
    })
    stats = verifier.stats()
    assert stats["runs"] == 1
    assert 0.0 <= stats["accept_rate"] <= 1.0


def test_materialise_attaches_verification_on_godot_output(tmp_path):
    forge, bp = _bp(tmp_path)
    out = forge.materialise(bp, target="godot")
    assert out["file_count"] > 0
    assert out["verification"]["accepted"] is True
    assert out["verification"]["score"] >= 0.7
    assert out["verification"]["reason"] == "accepted"
    assert out["verification"]["quality"]["metadata"]["kind"] == "forge"
    assert out["verification_stats"]["runs"] == 1
    rows = load_quality(root=tmp_path)
    assert rows and rows[-1]["surface"] == "forge"


def test_materialise_rejects_broken_emitter_and_records_failure(tmp_path, monkeypatch):
    forge, bp = _bp(tmp_path)

    def bad_emit(*args, **kwargs):
        return {"project.godot": "config_version=5\n"}

    monkeypatch.setattr("skeleton.forge.godot_emit.emit_godot", bad_emit)
    with pytest.raises(MaterialisationError) as exc:
        forge.materialise(bp, target="godot")
    assert "verification" in exc.value.context
    assert "verification_stats" in exc.value.context
    fail = latest_failure(root=tmp_path, surface="forge")
    assert fail["surface"] == "forge"
