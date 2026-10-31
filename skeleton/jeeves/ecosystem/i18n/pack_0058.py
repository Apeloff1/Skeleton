"""Locale pack 0058.
"""
from __future__ import annotations

PACK = "loc_0058"

def t(key: str) -> str:
    if not key:
        return ""
    return f"{PACK}:{key}"

def keys() -> list[str]:
    return ["title", "start", "options", "quit"]
