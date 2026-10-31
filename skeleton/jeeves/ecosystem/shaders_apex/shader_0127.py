"""Shader apex 0127.
"""
from __future__ import annotations

ID = "shader_apex_0127"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 127}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
