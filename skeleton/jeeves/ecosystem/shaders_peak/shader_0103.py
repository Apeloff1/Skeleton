"""Shader peak 0103.
"""
from __future__ import annotations

ID = "shader_peak_0103"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 103}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
