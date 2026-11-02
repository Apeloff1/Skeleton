"""Local AI Assetpipe ultra 0164.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "assetpipe_ultra_0164"

def describe() -> dict:
    return {"id": ID, "kind": "assetpipe", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 164 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 164 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (164 % 15) * 0.01, "notes": "refined"}
