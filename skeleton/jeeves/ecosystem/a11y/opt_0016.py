"""A11y option 0016.
"""
from __future__ import annotations

OPT = "a11y_0016"

def apply(enabled: bool) -> dict:
    return {"ok": True, "opt": OPT, "enabled": bool(enabled)}
