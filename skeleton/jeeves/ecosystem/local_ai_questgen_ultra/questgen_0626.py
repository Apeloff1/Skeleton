"""Local AI Questgen ultra 0626.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "questgen_ultra_0626"

def describe() -> dict:
    return {"id": ID, "kind": "questgen", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 626 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 626 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (626 % 15) * 0.01, "notes": "refined"}
