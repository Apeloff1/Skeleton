"""Local AI Orchestrator ultra 0581.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "orchestrator_ultra_0581"

def describe() -> dict:
    return {"id": ID, "kind": "orchestrator", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 581 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 581 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (581 % 15) * 0.01, "notes": "refined"}
