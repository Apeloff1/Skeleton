"""Shader prime 0124.
"""
from __future__ import annotations

ID = "shader_prime_0124"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 124}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
