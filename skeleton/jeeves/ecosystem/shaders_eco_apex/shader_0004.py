"""Shader eco_apex 0004.
"""
from __future__ import annotations

ID = "shader_eco_apex_0004"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 4}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
