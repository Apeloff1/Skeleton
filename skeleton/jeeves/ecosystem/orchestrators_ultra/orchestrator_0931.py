"""Local AI Orchestrator ultra 0931.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "orchestrator_ultra_0931"

def describe() -> dict:
    return {"id": ID, "kind": "orchestrator", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 931 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 931 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (931 % 15) * 0.01, "notes": "refined"}
