"""Snowball mass — persist chronicle/snowball.json. +25–40% per tick, cap 1.0."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def path(root: Optional[Path] = None) -> Path:
    base = Path(root) if root else Path(".")
    p = base / "chronicle" / "snowball.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load(root: Optional[Path] = None) -> Dict[str, Any]:
    p = path(root)
    if not p.is_file():
        return {"kind": "snowball", "mass": 0.0, "target": 1.0, "n": 0, "stored_prose": 0}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"kind": "snowball", "mass": 0.0, "target": 1.0, "n": 0, "stored_prose": 0}


def tick(root: Optional[Path] = None, *, delta: float = 0.30, critique: str = "ok") -> Dict[str, Any]:
    row = load(root)
    d = min(0.40, max(0.25, float(delta)))
    mass = min(1.0, float(row.get("mass") or 0) + d)
    row.update({
        "kind": "snowball",
        "mass": round(mass, 4),
        "target": 1.0,
        "n": int(row.get("n") or 0) + 1,
        "delta": d,
        "critique": str(critique or "ok")[:32],
        "stored_prose": 0,
    })
    path(root).write_text(json.dumps(row, indent=2), encoding="utf-8")
    return row


def card(root: Optional[Path] = None) -> Dict[str, Any]:
    row = load(root)
    return {
        "kind": "snowball",
        "mass": float(row.get("mass") or 0),
        "n": int(row.get("n") or 0),
        "stored_prose": 0,
    }
