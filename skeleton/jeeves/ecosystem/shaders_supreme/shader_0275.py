"""Shader supreme 0275.
"""
from __future__ import annotations

ID = "shader_supreme_0275"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 275}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
