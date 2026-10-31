"""Shader peak 0120.
"""
from __future__ import annotations

ID = "shader_peak_0120"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 120}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
