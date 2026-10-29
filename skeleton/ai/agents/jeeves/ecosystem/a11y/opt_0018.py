"""A11y option 0018.
"""
from __future__ import annotations

OPT = "a11y_0018"

def apply(enabled: bool) -> dict:
    return {"ok": True, "opt": OPT, "enabled": bool(enabled)}
