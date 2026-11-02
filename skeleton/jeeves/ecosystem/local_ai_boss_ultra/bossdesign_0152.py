"""Local AI Bossdesign ultra 0152.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "bossdesign_ultra_0152"

def describe() -> dict:
    return {"id": ID, "kind": "bossdesign", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 152 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 152 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (152 % 15) * 0.01, "notes": "refined"}
