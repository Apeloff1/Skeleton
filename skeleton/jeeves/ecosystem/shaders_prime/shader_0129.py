"""Shader prime 0129.
"""
from __future__ import annotations

ID = "shader_prime_0129"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 129}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
