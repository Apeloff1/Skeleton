"""Local AI Bossdesign ultra 0466.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "bossdesign_ultra_0466"

def describe() -> dict:
    return {"id": ID, "kind": "bossdesign", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 466 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 466 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (466 % 15) * 0.01, "notes": "refined"}
