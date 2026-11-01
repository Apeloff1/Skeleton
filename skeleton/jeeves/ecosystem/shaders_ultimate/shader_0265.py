"""Shader ultimate 0265.
"""
from __future__ import annotations

ID = "shader_ultimate_0265"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 265}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
