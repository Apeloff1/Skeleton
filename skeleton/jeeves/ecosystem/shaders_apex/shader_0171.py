"""Shader apex 0171.
"""
from __future__ import annotations

ID = "shader_apex_0171"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 171}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
