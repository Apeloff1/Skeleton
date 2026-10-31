"""Shader prime 0128.
"""
from __future__ import annotations

ID = "shader_prime_0128"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 128}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
