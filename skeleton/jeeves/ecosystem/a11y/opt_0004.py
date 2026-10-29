"""A11y option 0004.
"""
from __future__ import annotations

OPT = "a11y_0004"

def apply(enabled: bool) -> dict:
    return {"ok": True, "opt": OPT, "enabled": bool(enabled)}
