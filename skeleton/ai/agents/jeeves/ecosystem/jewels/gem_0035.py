"""Gem 0035.
"""
from __future__ import annotations

GEM = "gem_0035"

def cut(raw: str) -> dict:
    if not raw:
        return {"ok": False, "reason": "no_raw"}
    return {"ok": True, "gem": GEM, "quality": "fine"}
