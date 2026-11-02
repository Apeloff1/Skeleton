"""Local AI Critic ultra 0346.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "critic_ultra_0346"

def describe() -> dict:
    return {"id": ID, "kind": "critic", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 346 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 346 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (346 % 15) * 0.01, "notes": "refined"}
