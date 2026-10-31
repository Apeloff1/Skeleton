"""Shader peak 0027.
"""
from __future__ import annotations

ID = "shader_peak_0027"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 27}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
