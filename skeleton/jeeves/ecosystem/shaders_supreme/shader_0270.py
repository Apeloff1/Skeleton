"""Shader supreme 0270.
"""
from __future__ import annotations

ID = "shader_supreme_0270"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 270}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
