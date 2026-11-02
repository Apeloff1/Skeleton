"""Local AI Critic 0223.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "critic_local_0223"

def describe() -> dict:
    return {"id": ID, "kind": "critic", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 223 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 223 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (223 % 15) * 0.01, "notes": "refined"}
