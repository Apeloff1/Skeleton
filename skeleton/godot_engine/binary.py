"""godot_engine.binary — spec name for GB-9 locate()."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_POINTER = _REPO / "backend" / "godot.artifact.json"
_LOCAL = _REPO / "backend" / "godot"


def _pointer() -> dict:
    if _POINTER.is_file():
        try:
            return json.loads(_POINTER.read_text())
        except Exception:
            return {"hint": "unreadable pointer"}
    return {"hint": "set GODOT_BINARY or place backend/godot", "local_path": "backend/godot"}


def locate() -> dict:
    notes: list[str] = []
    env = os.environ.get("GODOT_BINARY", "").strip()
    path = None
    source = ""
    if env and Path(env).is_file():
        path, source = Path(env), "env"
    elif _LOCAL.is_file():
        path, source = _LOCAL, "repo"
    else:
        which = shutil.which("godot")
        if which:
            path, source = Path(which), "path"
        else:
            notes.append("no candidate")
    pointer = _pointer()
    if path is None:
        return {
            "kind": "godot-binary",
            "found": 0,
            "hit": 0,
            "hint": pointer.get("hint") or "missing godot binary",
            "pointer": pointer,
            "notes": notes,
            "stored_prose": 0,
        }
    return {
        "kind": "godot-binary",
        "found": 1,
        "hit": 1,
        "path": str(path),
        "source": source,
        "hint": "",
        "pointer": pointer,
        "stored_prose": 0,
    }


def binary_status() -> dict:
    card = locate()
    card["available"] = bool(card.get("found"))
    return card


def get_binary():
    card = locate()
    if not card.get("found"):
        raise FileNotFoundError(card.get("hint") or "No Godot binary")
    return card
