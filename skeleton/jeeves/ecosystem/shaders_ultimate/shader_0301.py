"""Shader ultimate 0301.
"""
from __future__ import annotations

ID = "shader_ultimate_0301"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 301}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
