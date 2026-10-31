"""Shader apex 0134.
"""
from __future__ import annotations

ID = "shader_apex_0134"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 134}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
