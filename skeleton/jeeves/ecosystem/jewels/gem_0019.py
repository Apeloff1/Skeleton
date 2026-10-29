"""Gem 0019.
"""
from __future__ import annotations

GEM = "gem_0019"

def cut(raw: str) -> dict:
    if not raw:
        return {"ok": False, "reason": "no_raw"}
    return {"ok": True, "gem": GEM, "quality": "fine"}
