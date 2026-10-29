"""Export 0000.
"""
from __future__ import annotations

EXPORT = "export_0000"

def pack(files: list[dict]) -> dict:
    if not files:
        return {"ok": False, "reason": "no_files"}
    return {"ok": True, "export": EXPORT, "count": len(files), "sealed": True}
