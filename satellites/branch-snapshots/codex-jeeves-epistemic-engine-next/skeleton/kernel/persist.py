"""Persist last orchestrator walk next to the organism root."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def path(root: Optional[Path] = None) -> Path:
    base = Path(root) if root else Path(".")
    return base / "chronicle" / "orch.json"


def save(card: Dict[str, Any], *, root: Optional[Path] = None) -> Path:
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    slim = {
        "kind": card.get("kind"),
        "runs": card.get("runs"),
        "n": card.get("n"),
        "route": card.get("route"),
        "trace": card.get("trace"),
        "stored_prose": 0,
    }
    p.write_text(json.dumps(slim, indent=2, default=str), encoding="utf-8")
    return p


def board_path(root: Optional[Path] = None) -> Path:
    base = Path(root) if root else Path(".")
    return base / "chronicle" / "board.json"


def prev_board_path(root: Optional[Path] = None) -> Path:
    base = Path(root) if root else Path(".")
    return base / "chronicle" / "board.prev.json"


def save_board(card: Dict[str, Any], *, root: Optional[Path] = None) -> Path:
    cur = board_path(root)
    prev = prev_board_path(root)
    cur.parent.mkdir(parents=True, exist_ok=True)
    if cur.is_file():
        prev.write_text(cur.read_text(encoding="utf-8"), encoding="utf-8")
    slim = {"kind": "board", "n": card.get("n"), "names": list((card.get("rows") or {}).keys()), "stored_prose": 0}
    cur.write_text(json.dumps(slim, indent=2), encoding="utf-8")
    return cur


def load(*, root: Optional[Path] = None) -> Dict[str, Any]:
    p = path(root)
    if not p.is_file():
        return {"kind": "orch-persist", "runs": 0, "stored_prose": 0}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"kind": "orch-persist", "runs": 0, "stored_prose": 0}


def gov_path(root: Optional[Path] = None) -> Path:
    base = Path(root) if root else Path(".")
    return base / "chronicle" / "gov.json"


def save_gov(card: Dict[str, Any], *, root: Optional[Path] = None) -> Path:
    p = gov_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    slim = {
        "kind": "kernel-gov",
        "action": card.get("action"),
        "pressure": card.get("pressure"),
        "profile": card.get("profile"),
        "was": card.get("was"),
        "rebuilt": card.get("rebuilt"),
        "stored_prose": 0,
    }
    p.write_text(json.dumps(slim, indent=2), encoding="utf-8")
    return p


def load_gov(*, root: Optional[Path] = None) -> Dict[str, Any]:
    p = gov_path(root)
    if not p.is_file():
        return {"kind": "kernel-gov", "action": "hold", "stored_prose": 0}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"kind": "kernel-gov", "action": "hold", "stored_prose": 0}
