"""Local AI Worldsim 0234.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "worldsim_local_0234"

def describe() -> dict:
    return {"id": ID, "kind": "worldsim", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 234 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 234 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (234 % 15) * 0.01, "notes": "refined"}
