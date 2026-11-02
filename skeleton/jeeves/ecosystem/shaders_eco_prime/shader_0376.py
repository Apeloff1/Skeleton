"""Shader eco_prime 0376.
"""
from __future__ import annotations

ID = "shader_eco_prime_0376"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 376}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
