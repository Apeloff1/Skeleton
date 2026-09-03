"""Calendar — last day, dump inventory, last gov. No new loops."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def _read(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def card(root: Optional[Path] = None) -> Dict[str, Any]:
    base = Path(root) if root else Path(".")
    ch = base / "chronicle"
    day = _read(ch / "day.json")
    rot = _read(ch / "rot.json")
    gov = _read(ch / "gov.json")
    inv: Dict[str, Any] = {}
    try:
        from skeleton.organism.chronicle.dump import inventory
        inv = inventory(root)
    except Exception:
        inv = {}
    return {
        "kind": "calendar",
        "day_heads": day.get("heads") or [],
        "day_n": day.get("n") or 0,
        "rot": rot.get("verdict"),
        "gov": gov.get("action"),
        "profile": gov.get("profile"),
        "dumps": inv.get("n") or 0,
        "years": inv.get("years") or [],
        "ctx_n": __import__("skeleton.organism.context_step", fromlist=["last"]).last(root).get("n") or 0,
        "stored_prose": 0,
    }
