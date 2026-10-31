"""A11y option 0008.
"""
from __future__ import annotations

OPT = "a11y_0008"

def apply(enabled: bool) -> dict:
    return {"ok": True, "opt": OPT, "enabled": bool(enabled)}
