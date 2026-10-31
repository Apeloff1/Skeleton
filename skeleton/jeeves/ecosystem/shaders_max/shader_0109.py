"""Shader max 0109.
"""
from __future__ import annotations

ID = "shader_max_0109"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 109}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
