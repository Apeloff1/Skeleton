"""Shader supreme 0274.
"""
from __future__ import annotations

ID = "shader_supreme_0274"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 274}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
