"""Shader ultimate 0251.
"""
from __future__ import annotations

ID = "shader_ultimate_0251"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 251}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
