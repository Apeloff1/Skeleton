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


def load(*, root: Optional[Path] = None) -> Dict[str, Any]:
    p = path(root)
    if not p.is_file():
        return {"kind": "orch-persist", "runs": 0, "stored_prose": 0}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"kind": "orch-persist", "runs": 0, "stored_prose": 0}
