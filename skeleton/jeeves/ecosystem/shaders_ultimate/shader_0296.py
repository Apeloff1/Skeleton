"""Shader ultimate 0296.
"""
from __future__ import annotations

ID = "shader_ultimate_0296"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 296}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
