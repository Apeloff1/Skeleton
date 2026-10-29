"""Export 0012.
"""
from __future__ import annotations

EXPORT = "export_0012"

def pack(files: list[dict]) -> dict:
    if not files:
        return {"ok": False, "reason": "no_files"}
    return {"ok": True, "export": EXPORT, "count": len(files), "sealed": True}
