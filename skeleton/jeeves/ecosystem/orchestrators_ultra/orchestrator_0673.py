"""Local AI Orchestrator ultra 0673.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "orchestrator_ultra_0673"

def describe() -> dict:
    return {"id": ID, "kind": "orchestrator", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 673 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 673 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (673 % 15) * 0.01, "notes": "refined"}
