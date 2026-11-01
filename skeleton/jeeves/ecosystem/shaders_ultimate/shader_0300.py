"""Shader ultimate 0300.
"""
from __future__ import annotations

ID = "shader_ultimate_0300"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 300}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
