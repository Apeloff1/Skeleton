"""Export 0044.
"""
from __future__ import annotations

EXPORT = "export_0044"

def pack(files: list[dict]) -> dict:
    if not files:
        return {"ok": False, "reason": "no_files"}
    return {"ok": True, "export": EXPORT, "count": len(files), "sealed": True}
