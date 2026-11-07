"""Godot 4.3 export driver: forge -> export -> boot (real binary when present)."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "godot_export_build.py"
TEMPLATES = Path.home() / ".local/share/godot/export_templates/4.3.stable/linux_release.x86_64"


def _load():
    spec = importlib.util.spec_from_file_location("godot_export_build", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _godot() -> str | None:
    for env in ("SKELETON_GODOT_BIN", "GODOT_BINARY"):
        value = os.environ.get(env)
        if value and Path(value).is_file():
            return value
    return shutil.which("godot4") or shutil.which("godot")


def test_forge_only_writes_exportable_projects(tmp_path):
    mod = _load()
    assert mod.main(["--out", str(tmp_path), "--forge-only"]) == 0
    manifest = json.loads((tmp_path / "export_manifest.json").read_text())
    assert set(manifest["builds"]) == set(mod.DEFAULT_ARCHETYPES)
    for archetype, entry in manifest["builds"].items():
        assert len(entry["stages"]) == 10
        project = tmp_path / archetype
        assert (project / "project.godot").is_file()
        presets = (project / "export_presets.cfg").read_text()
        assert 'name="Linux"' in presets and "builds/linux/game.x86_64" in presets
        assert (project / "CONTEXT_LEDGER.json").is_file()


def test_unknown_godot_binary_fails_closed(tmp_path):
    mod = _load()
    with pytest.raises((FileNotFoundError, SystemExit, PermissionError)):
        mod.main(["--out", str(tmp_path), "--archetype", "extraction", "--godot", str(tmp_path / "no-godot")])


@pytest.mark.skipif(_godot() is None or not TEMPLATES.is_file(), reason="Godot 4.3 binary/templates not installed")
def test_real_export_produces_bootable_linux_build(tmp_path):
    mod = _load()
    assert mod.main(["--out", str(tmp_path), "--archetype", "extraction", "--godot", _godot(), "--boot-frames", "60"]) == 0
    entry = json.loads((tmp_path / "export_manifest.json").read_text())["builds"]["extraction"]["export"]
    exe = tmp_path / "extraction" / entry["executable"]
    assert exe.is_file() and os.access(exe, os.X_OK)
    assert entry["executable_bytes"] > 1_000_000
    assert entry["pck_bytes"] > 0
    assert entry["boot_errors"] == []
