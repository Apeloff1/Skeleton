"""Shader supreme 0250.
"""
from __future__ import annotations

ID = "shader_supreme_0250"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 250}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
