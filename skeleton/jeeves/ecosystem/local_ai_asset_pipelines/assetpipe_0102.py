"""Local AI Assetpipe 0102.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "assetpipe_local_0102"

def describe() -> dict:
    return {"id": ID, "kind": "assetpipe", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 102 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 102 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (102 % 15) * 0.01, "notes": "refined"}
