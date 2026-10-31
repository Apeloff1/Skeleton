"""Subtitle 0010.
"""
from __future__ import annotations

SUB = "sub_0010"

def show(text: str) -> dict:
    if not text:
        return {"ok": False, "reason": "empty"}
    return {"ok": True, "sub": SUB, "text": text[:240]}
