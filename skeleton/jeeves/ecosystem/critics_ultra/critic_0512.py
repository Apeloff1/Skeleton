"""Local AI Critic ultra 0512.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "critic_ultra_0512"

def describe() -> dict:
    return {"id": ID, "kind": "critic", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 512 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 512 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (512 % 15) * 0.01, "notes": "refined"}
