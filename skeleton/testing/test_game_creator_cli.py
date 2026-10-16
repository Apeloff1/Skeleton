"""Game creator CLI contract tests; no Godot installation or model required."""
from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from skeleton.developer.game_cli import run_game_cli
from skeleton.forge.projector import write_project


def workspace(tmp_path: Path) -> Path:
    result = run_game_cli(["init", "original-world", "--dir", str(tmp_path),
                           "--vision", "Original forest exploration", "--era", "extraction_now"])
    assert result["ok"], result
    return tmp_path / "original-world"


def emit(root: Path) -> None:
    write_project(root / "build" / "godot", {
        "project.godot": 'config_version=5\n[application]\nrun/main_scene="res://main.tscn"\n',
        "main.tscn": '[gd_scene format=3]\n[node name="Main" type="Node"]\n',
    })


def test_game_catalog_matches_existing_forge_catalog():
    from skeleton.forge.eras import list_eras
    catalog = run_game_cli(["catalog"])
    assert catalog["ok"] and catalog["eras"] == list_eras()
    assert {"auto", "extraction"} <= set(catalog["archetypes"])
    assert catalog["build_targets"] == ["godot"]


def test_game_workspace_init_and_inspect(tmp_path: Path):
    root = workspace(tmp_path)
    assert (root / "assets").is_dir()
    assert (root / "design").is_dir()
    assert (root / "tests").is_dir()
    assert json.loads((root / "skeleton.game.json").read_text())["vision"] == "Original forest exploration"
    assert run_game_cli(["info", "--project", str(root)])["config"]["schema"] == "skeleton.game.workspace.v1"
    assert run_game_cli(["assets", "--project", str(root)])["inventory"]["count"] == 0
    assert not run_game_cli(["init", "original-world", "--dir", str(tmp_path)])["ok"]


def test_invalid_archetype_fails_before_side_effects(tmp_path: Path):
    result = run_game_cli(["init", "bad-game", "--dir", str(tmp_path),
                           "--archetype", "not-an-archetype"])
    assert result["ok"] is False
    assert not (tmp_path / "bad-game").exists()


def test_game_dry_run_has_no_effect_and_rejects_traversal(tmp_path: Path):
    result = run_game_cli(["init", "planned-game", "--dir", str(tmp_path), "--dry-run"])
    assert result["ok"] and result["dry_run"]
    assert not (tmp_path / "planned-game").exists()
    for unsafe in ("..", "../other", "not/a/name"):
        assert not run_game_cli(["init", unsafe, "--dir", str(tmp_path)])["ok"]


def test_verification_and_package_are_source_receipts_not_native_claims(tmp_path: Path):
    root = workspace(tmp_path)
    emit(root)
    verified = run_game_cli(["verify", "--project", str(root)])
    assert verified["ok"] and verified["source_manifest"]["file_count"] == 2
    dry = run_game_cli(["package", "--project", str(root), "--dry-run"])
    assert dry["ok"] and dry["native_binary"] is False
    assert not (root / "dist").exists()
    result = run_game_cli(["package", "--project", str(root)])
    assert result["ok"]
    with zipfile.ZipFile(result["archive"]) as archive:
        assert "project.godot" in archive.namelist()
        assert "FORGE_MANIFEST.json" in archive.namelist()
    assert not run_game_cli(["package", "--project", str(root)])["ok"]


def test_verify_detects_content_tampering_and_prevents_package(tmp_path: Path):
    root = workspace(tmp_path)
    emit(root)
    (root / "build" / "godot" / "main.tscn").write_text("modified", encoding="utf-8")
    result = run_game_cli(["verify", "--project", str(root)])
    assert result["ok"] is False and "changed Forge source" in result["error"]
    assert run_game_cli(["package", "--project", str(root)])["ok"] is False


def test_verify_rejects_unsafe_windows_path_before_file_io(tmp_path: Path):
    root = workspace(tmp_path)
    emit(root)
    receipt_path = root / "build" / "godot" / "FORGE_MANIFEST.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["sha256"]["C:/escape.gd"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    result = run_game_cli(["verify", "--project", str(root)])
    assert result["ok"] is False
    assert "unsafe Forge file list" in result["error"]


def test_assets_inventory_is_content_addressed_and_symlink_safe(tmp_path: Path):
    root = workspace(tmp_path)
    (root / "assets" / "icon.png").write_bytes(b"\x89PNGexample")
    item = run_game_cli(["assets", "--project", str(root)])
    assert item["ok"] and item["inventory"]["count"] == 1
    assert len(item["inventory"]["sha256"]["icon.png"]) == 64
    (root / "assets" / "unsafe").symlink_to(tmp_path, target_is_directory=True)
    assert not run_game_cli(["assets", "--project", str(root)])["ok"]


def test_game_doctor_reports_missing_godot_without_fake_readiness(tmp_path: Path, monkeypatch):
    root = workspace(tmp_path)
    monkeypatch.setattr("skeleton.forge.playtest.resolve_binary",
                        lambda: (None, "missing-godot-binary", False))
    casual = run_game_cli(["doctor", "--project", str(root)])
    assert casual["ok"] and not casual["godot"]["found"]
    strict = run_game_cli(["doctor", "--project", str(root), "--require-godot"])
    assert strict["ok"] is False and strict["problems"]


def test_required_playtest_uses_existing_playtest_gate(tmp_path: Path, monkeypatch):
    root = workspace(tmp_path)
    emit(root)
    monkeypatch.setattr("skeleton.forge.playtest.playtest",
                        lambda files, **kwargs: {"status": "unavailable", "passed": False})
    result = run_game_cli(["playtest", "--project", str(root)])
    assert result["ok"] is False
    assert result["playtest"]["status"] == "unavailable"
    monkeypatch.setattr("skeleton.forge.playtest.playtest",
                        lambda files, **kwargs: {"status": "passed", "passed": True})
    assert run_game_cli(["playtest", "--project", str(root)])["ok"] is True



def test_build_delegates_to_canonical_gameforge_without_replacement(tmp_path: Path, monkeypatch):
    import sys
    from types import SimpleNamespace

    root = workspace(tmp_path)
    captured: dict[str, object] = {}

    class FakeForge:
        @staticmethod
        def live():
            return FakeForge()

        def execute(self, vision, **kwargs):
            captured["vision"] = vision
            captured.update(kwargs)
            return {
                "succeeded": True,
                "source_manifest": {"sha256": "a" * 64},
                "run": {"stages": []},
                "playtest": {"status": "unavailable", "passed": False},
            }

    monkeypatch.setitem(sys.modules, "skeleton.context.pipeline",
                        SimpleNamespace(GameForgeRun=FakeForge))
    result = run_game_cli(["build", "--project", str(root), "--overwrite",
                           "--playtest", "auto", "--repair-mode", "suggest"])
    assert result["ok"]
    assert captured["vision"] == "Original forest exploration"
    assert captured["era"] == "extraction_now"
    assert captured["archetype"] == "auto"
    assert captured["target"] == "godot"
    assert captured["overwrite"] is True
    assert captured["playtest"] == "auto"
    assert captured["repair_mode"] == "suggest"
    assert captured["project_root"] == str(root / "build" / "godot")


def test_cli_integration_and_exit_codes(tmp_path: Path, capsys):
    from skeleton.developer.cli import main
    assert main(["game", "init", "playground", "--dir", str(tmp_path)]) == 0
    assert main(["game", "verify", "--project", str(tmp_path / "playground")]) == 1
    out = capsys.readouterr().out
    assert '"action": "init"' in out
    assert '"action": "verify"' in out
