"""Local AI Assetpipe 0424.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "assetpipe_local_0424"

def describe() -> dict:
    return {"id": ID, "kind": "assetpipe", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 424 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 424 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (424 % 15) * 0.01, "notes": "refined"}
