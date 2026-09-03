"""Forge verification gate tests.

Covers project acceptance/rejection over emitted Godot file sets and the
materialisation chokepoint that now enforces the verifier.
"""

from __future__ import annotations

import pytest

from skeleton.intelligence.forge_verifier import ForgeVerifier
from skeleton.kernel.errors import MaterialisationError


def _bp():
    from skeleton.forge.universal import Forge

    forge = Forge()
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
    assert not report.project_issues
    assert report.file_reports


def test_forge_verifier_rejects_missing_required_file():
    from skeleton.forge.godot_emit import emit_godot
    from skeleton.forge.eras import compile_era

    files = emit_godot(compile_era("extraction_now"), title="VerifierGate")
    files.pop("project.godot")
    report = ForgeVerifier().verify(files)
    assert not report.accepted
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


def test_gdscript_verifier_accepts_func_without_python_def():
    report = ForgeVerifier()._verify_gdscript(
        "scripts/world/door.gd",
        'extends Node\nfunc open():\n    return true\n',
        request="door"
    )
    assert report.score >= 0.7
    assert "no func definition" not in report.issues


def test_gdscript_verifier_penalizes_missing_extends():
    report = ForgeVerifier()._verify_gdscript(
        "scripts/world/door.gd",
        'func open():\n    return true\n',
        request="door"
    )
    assert report.score < 0.7
    assert "missing extends" in report.issues


def test_materialise_attaches_verification_on_godot_output():
    forge, bp = _bp()
    out = forge.materialise(bp, target="godot")
    assert out["file_count"] > 0
    assert out["verification"]["accepted"] is True
    assert out["verification"]["score"] >= 0.7


def test_materialise_rejects_broken_emitter(monkeypatch):
    forge, bp = _bp()

    def bad_emit(*args, **kwargs):
        return {"project.godot": "config_version=5\n"}

    monkeypatch.setattr("skeleton.forge.godot_emit.emit_godot", bad_emit)
    with pytest.raises(MaterialisationError) as exc:
        forge.materialise(bp, target="godot")
    assert "verification" in exc.value.context
