"""Shader supreme 0217.
"""
from __future__ import annotations

ID = "shader_supreme_0217"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 217}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
