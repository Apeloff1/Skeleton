"""Local AI Assetpipe ultra 0755.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "assetpipe_ultra_0755"

def describe() -> dict:
    return {"id": ID, "kind": "assetpipe", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 755 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 755 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (755 % 15) * 0.01, "notes": "refined"}
