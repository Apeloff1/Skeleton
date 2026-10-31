"""Shader apex 0136.
"""
from __future__ import annotations

ID = "shader_apex_0136"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 136}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
