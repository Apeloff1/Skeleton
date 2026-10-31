"""A11y option 0000.
"""
from __future__ import annotations

OPT = "a11y_0000"

def apply(enabled: bool) -> dict:
    return {"ok": True, "opt": OPT, "enabled": bool(enabled)}
