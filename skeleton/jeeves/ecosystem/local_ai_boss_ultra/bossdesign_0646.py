"""Local AI Bossdesign ultra 0646.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "bossdesign_ultra_0646"

def describe() -> dict:
    return {"id": ID, "kind": "bossdesign", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 646 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 646 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (646 % 15) * 0.01, "notes": "refined"}
