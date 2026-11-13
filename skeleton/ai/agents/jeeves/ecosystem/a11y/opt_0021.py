"""A11y option 0021.
"""
from __future__ import annotations

OPT = "a11y_0021"

def apply(enabled: bool) -> dict:
    return {"ok": True, "opt": OPT, "enabled": bool(enabled)}
