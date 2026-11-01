"""Shader ultimate 0267.
"""
from __future__ import annotations

ID = "shader_ultimate_0267"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 267}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
