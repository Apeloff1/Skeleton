"""Unit tests for scripts/check_godot_tree.py (stdlib only, no Godot binary)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_godot_tree.py"
_spec = importlib.util.spec_from_file_location("check_godot_tree", SCRIPT)
assert _spec and _spec.loader
cgt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cgt)

PROJECT = (
    "; Engine configuration file.\n"
    "config_version=5\n\n"
    "[application]\n"
    'config/name="T"\n'
    'run/main_scene="res://scenes/main.tscn"\n\n'
    "[autoload]\n"
    'EventBus="*res://scripts/event_bus.gd"\n'
)
SCENE = (
    "[gd_scene load_steps=2 format=3]\n\n"
    '[ext_resource type="Script" path="res://scripts/player.gd" id="1"]\n\n'
    '[node name="Main" type="Node2D"]\n'
    'script = ExtResource("1")\n'
)


def _write(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    _write(tmp_path, "project.godot", PROJECT)
    _write(tmp_path, "scenes/main.tscn", SCENE)
    _write(tmp_path, "scripts/player.gd", 'extends Node2D\nvar s = "res://scenes/%s.tscn" % "main"\n')
    _write(tmp_path, "scripts/event_bus.gd", 'extends Node\nconst DIR = "res://scenes/" + "x"\n')
    return tmp_path


def test_clean_tree_passes(tree: Path) -> None:
    report = cgt.check_tree(tree)
    assert report["ok"] is True, report["problems"]
    assert report["scenes"] == ["scenes/main.tscn"]
    assert report["main_scene"] == "res://scenes/main.tscn"
    assert report["autoloads"] == 1
    assert report["ext_resources"] == 1
    assert report["dynamic_refs"] == 2


def test_missing_project_godot_fails(tree: Path) -> None:
    (tree / "project.godot").unlink()
    report = cgt.check_tree(tree)
    assert not report["ok"]
    assert "missing project.godot" in report["problems"]


def test_no_scene_fails(tree: Path) -> None:
    (tree / "scenes/main.tscn").unlink()
    problems = cgt.check_tree(tree)["problems"]
    assert any("at least 1 .tscn" in p for p in problems)
    assert any("run/main_scene does not resolve" in p for p in problems)


def test_missing_script_fails(tree: Path) -> None:
    (tree / "scripts/player.gd").unlink()
    problems = cgt.check_tree(tree)["problems"]
    assert any("missing ext_resource res://scripts/player.gd" in p for p in problems)


def test_missing_autoload_fails(tree: Path) -> None:
    (tree / "scripts/event_bus.gd").unlink()
    problems = cgt.check_tree(tree)["problems"]
    assert any(p.startswith("autoload EventBus") for p in problems)


def test_dangling_literal_reference_fails(tree: Path) -> None:
    _write(tree, "scripts/extra.gd", 'extends Node\nvar p = preload("res://scenes/ghost.tscn")\n')
    problems = cgt.check_tree(tree)["problems"]
    assert any("missing res:// reference res://scenes/ghost.tscn" in p for p in problems)


def test_escaping_reference_fails(tree: Path) -> None:
    _write(tree, "scripts/extra.gd", 'extends Node\nvar p = load("res://../outside.gd")\n')
    problems = cgt.check_tree(tree)["problems"]
    assert any("escapes the tree" in p for p in problems)


def test_script_ext_resource_must_be_gd(tree: Path) -> None:
    _write(tree, "scripts/not_code.txt", "x")
    _write(tree, "scenes/main.tscn", SCENE.replace("res://scripts/player.gd", "res://scripts/not_code.txt"))
    problems = cgt.check_tree(tree)["problems"]
    assert any("is not a .gd file" in p for p in problems)


def test_cli_exit_codes_and_json(tree: Path, tmp_path_factory, capsys) -> None:
    assert cgt.main([str(tree), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True and "elapsed_ms" in payload
    empty = tmp_path_factory.mktemp("empty")
    assert cgt.main([str(empty)]) == 1
    assert "FAIL" in capsys.readouterr().out
