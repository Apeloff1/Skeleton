"""Local AI Critic 0024.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "critic_local_0024"

def describe() -> dict:
    return {"id": ID, "kind": "critic", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 24 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 24 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (24 % 15) * 0.01, "notes": "refined"}
