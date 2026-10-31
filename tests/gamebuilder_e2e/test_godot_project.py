"""Materialised Godot 4 project files are structurally sound."""
from __future__ import annotations

import json

import pytest

from tests.gamebuilder_e2e.conftest import build, golden

REQUIRED = (
    "project.godot",
    "export_presets.cfg",
    "data/design_spec.json",
    "data/content_bundle.json",
    "data/build_plan.json",
    "scripts/autoloads/core_loop.gd",
    "scripts/autoloads/game_state.gd",
    "scripts/player/player_controller.gd",
)


def test_required_files(genre):
    names = set(build(golden(genre))["files"])
    assert [n for n in REQUIRED if n not in names] == []


def test_file_names_mirror_files(genre):
    result = build(golden(genre))
    assert sorted(result["file_names"]) == sorted(result["files"])


def test_no_empty_files(genre):
    files = build(golden(genre))["files"]
    assert [n for n, body in files.items() if not str(body).strip()] == []


def test_paths_are_relative_and_safe(genre):
    for name in build(golden(genre))["files"]:
        assert not name.startswith("/")
        assert ".." not in name.split("/")
        assert "\\" not in name


def test_json_data_parses(genre):
    files = build(golden(genre))["files"]
    for name in (n for n in files if n.endswith(".json")):
        json.loads(files[name])


def test_design_spec_json_matches_result(genre):
    result = build(golden(genre))
    on_disk = json.loads(result["files"]["data/design_spec.json"])
    assert on_disk["spec_id"] == result["spec"]["spec_id"]
    assert on_disk["genre"] == genre


def test_gdscript_files_extend_something(genre):
    files = build(golden(genre))["files"]
    for name in (n for n in files if n.endswith(".gd")):
        assert "extends " in files[name], name


def test_gdscript_brackets_balanced(genre):
    files = build(golden(genre))["files"]
    for name in (n for n in files if n.endswith(".gd")):
        body = files[name]
        for open_, close in ("()", "[]", "{}"):
            assert body.count(open_) == body.count(close), (name, open_)


def test_project_godot_declares_autoloads(genre):
    files = build(golden(genre))["files"]
    project = files["project.godot"]
    assert "config_version=5" in project
    assert "[autoload]" in project
    for name in (n for n in files if n.startswith("scripts/autoloads/")):
        stem = name.rsplit("/", 1)[1][:-3]
        assert f"res://{name}" in project, stem


def test_scenes_reference_existing_scripts(genre):
    files = build(golden(genre))["files"]
    for name in (n for n in files if n.endswith(".tscn")):
        for line in files[name].splitlines():
            if 'type="Script"' in line and 'path="res://' in line:
                ref = line.split('path="res://', 1)[1].split('"', 1)[0]
                assert ref in files, (name, ref)
