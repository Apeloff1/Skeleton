"""Local AI Worldsim 0358.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "worldsim_local_0358"

def describe() -> dict:
    return {"id": ID, "kind": "worldsim", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 358 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 358 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (358 % 15) * 0.01, "notes": "refined"}
