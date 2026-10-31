"""Shader peak 0123.
"""
from __future__ import annotations

ID = "shader_peak_0123"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 123}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
