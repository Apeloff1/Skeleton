"""Local AI Worldsim ultra 0888.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "worldsim_ultra_0888"

def describe() -> dict:
    return {"id": ID, "kind": "worldsim", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 888 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 888 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (888 % 15) * 0.01, "notes": "refined"}
