"""Portable source parity contract for CLI/HTTP/shared-command GameForge."""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from skeleton.__main__ import main
from skeleton.app.runtime.runtime_commands import _run_handler
from skeleton.context.pipeline import GameForgeRun
from skeleton.forge.projector import write_project
from skeleton.forge.source_manifest import source_manifest


def test_manifest_is_stable_under_source_iteration_order_and_changes():
    files = {"project.godot": "[application]\n", "data/rooms.json": "{}"}
    a = source_manifest(files)
    b = source_manifest(dict(reversed(list(files.items()))))
    assert a == b
    assert a["file_count"] == 2
    assert a["files"]["project.godot"] == hashlib.sha256(
        files["project.godot"].encode("utf-8")).hexdigest()
    assert source_manifest({**files, "data/rooms.json": '{"x":1}'})["sha256"] != a["sha256"]


@pytest.mark.parametrize("bad", [{None:"text"}, {"a":123}, {42:"hi"}])
def test_manifest_does_not_silently_stringify_invalid_sources(bad):
    with pytest.raises((TypeError, ValueError)):
        source_manifest(bad)


def test_materialized_manifest_uses_same_source_digest(tmp_path):
    files = {"project.godot": "[application]\n", "data/rooms.json": "{}"}
    emitted = write_project(tmp_path / "game", files)
    expected = source_manifest(files)
    assert emitted["sha256"] == expected["files"]
    assert emitted["source_sha256"] == expected["sha256"]
    persisted = json.loads((tmp_path / "game" / "FORGE_MANIFEST.json").read_text())
    assert persisted["source_sha256"] == expected["sha256"]


def test_same_creator_fixture_has_same_manifest_via_cli_and_command(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("SKELETON_COCKPIT_STATE", str(tmp_path / "operator.json"))
    vision = "an original quiet village"
    answers = {"pace": "unhurried", "genre": "rpg"}
    # The CLI's real GameForgeRun.live binds app-global Jeeves; use a new
    # unshared runner for both transports to compare their creator contract.
    with patch.object(GameForgeRun, "live",
                      side_effect=lambda **kw: GameForgeRun(**kw)):
        rc = main(["run", vision, "--answers", json.dumps(answers), "--json"])
    cli = json.loads(capsys.readouterr().out)
    assert rc == 0, cli.get("failed_stages")
    state = SimpleNamespace(gameforge=object())
    api = _run_handler(state)({
        "target": "godot", "vision": vision, "answers": answers,
        "playtest": "off", "repair_mode": "apply",
    })["game"]
    assert api["succeeded"] is True, api["run"]
    assert cli["source_manifest"] == api["source_manifest"]
    assert source_manifest(api["files"]) == cli["source_manifest"]
