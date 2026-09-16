"""GB-9 standalone — does not import skeleton package __init__."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "skeleton" / "godot_engine" / "binary.py"


def _load():
    spec = importlib.util.spec_from_file_location("godot_engine_binary", MOD)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_locate_card_schema():
    card = _load().locate()
    assert card["kind"] == "godot-binary"
    assert card["stored_prose"] == 0
    assert card["found"] in (0, 1)
    assert "hint" in card


def test_locate_missing(monkeypatch, tmp_path):
    mod = _load()
    monkeypatch.delenv("GODOT_BINARY", raising=False)
    monkeypatch.setattr(mod, "_LOCAL", tmp_path / "no-godot")
    monkeypatch.setattr(mod.shutil, "which", lambda _n: None)
    card = mod.locate()
    assert card["found"] == 0
    assert card["stored_prose"] == 0
    assert card["hint"]


def test_pointer_tracked():
    listed = subprocess.check_output(
        ["git", "ls-files", "backend/godot", "backend/godot.artifact.json"],
        cwd=ROOT,
        text=True,
    )
    assert "godot.artifact.json" in listed
    assert "backend/godot\n" not in listed and listed.strip() != "backend/godot"
