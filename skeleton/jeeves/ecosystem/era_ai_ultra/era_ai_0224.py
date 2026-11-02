"""Local AI Era_Ai ultra 0224.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "era_ai_ultra_0224"

def describe() -> dict:
    return {"id": ID, "kind": "era_ai", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 224 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 224 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (224 % 15) * 0.01, "notes": "refined"}
