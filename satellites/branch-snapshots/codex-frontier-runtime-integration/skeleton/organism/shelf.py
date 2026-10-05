"""Persist organismer state across processes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from skeleton.cortex.laws import check
from skeleton.organism.paths import state_path


def save(org, *, root: Optional[Path] = None) -> Dict[str, Any]:
    payload = check({
        "kind": "organism-state",
        "G": float(org.G),
        "steps": int(org.steps),
        "errors": int(org.errors),
        "galaxy_pulses": int(getattr(org.galaxy, "pulses", 0) or 0),
        "log": list(org.log[-32:]),
        "genos": org.genos.snapshot(),
        "last_health": dict(getattr(org, "last_health", {}) or {}),
        "stored_prose": 0,
    })
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return {"path": str(path), "G": payload["G"], "steps": payload["steps"]}


def load(org, *, root: Optional[Path] = None) -> Dict[str, Any]:
    path = state_path(root)
    if not path.exists():
        return {"loaded": 0}
    data = json.loads(path.read_text(encoding="utf-8"))
    org.steps = int(data.get("steps") or 0)
    org.errors = int(data.get("errors") or 0)
    org.log = list(data.get("log") or [])
    org.genos.restore(data.get("genos"))
    return {"loaded": 1, "G": org.G, "steps": org.steps}
