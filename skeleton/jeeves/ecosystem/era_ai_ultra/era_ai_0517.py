"""Local AI Era_Ai ultra 0517.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "era_ai_ultra_0517"

def describe() -> dict:
    return {"id": ID, "kind": "era_ai", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 517 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 517 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (517 % 15) * 0.01, "notes": "refined"}
