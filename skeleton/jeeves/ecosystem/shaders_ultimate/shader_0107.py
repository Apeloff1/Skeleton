"""Shader ultimate 0107.
"""
from __future__ import annotations

ID = "shader_ultimate_0107"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 107}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
