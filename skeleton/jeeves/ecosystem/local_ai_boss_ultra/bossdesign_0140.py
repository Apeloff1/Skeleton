"""Local AI Bossdesign ultra 0140.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "bossdesign_ultra_0140"

def describe() -> dict:
    return {"id": ID, "kind": "bossdesign", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 140 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 140 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (140 % 15) * 0.01, "notes": "refined"}
