"""Local AI Assetpipe 0167.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "assetpipe_local_0167"

def describe() -> dict:
    return {"id": ID, "kind": "assetpipe", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 167 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 167 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (167 % 15) * 0.01, "notes": "refined"}
