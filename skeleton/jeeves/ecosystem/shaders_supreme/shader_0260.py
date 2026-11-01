"""Shader supreme 0260.
"""
from __future__ import annotations

ID = "shader_supreme_0260"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 260}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
