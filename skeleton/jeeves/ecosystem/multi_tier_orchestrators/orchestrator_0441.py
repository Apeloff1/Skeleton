"""Local AI Orchestrator 0441.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "orchestrator_local_0441"

def describe() -> dict:
    return {"id": ID, "kind": "orchestrator", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 441 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 441 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (441 % 15) * 0.01, "notes": "refined"}
