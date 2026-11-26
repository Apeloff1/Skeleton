"""
Decade dump completeness, unified CLI discovery, and doctor-cycle pin.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

CLI = ["rotors.json", "loop.jsonl", "bound.jsonl"]


def process(data: dict) -> dict:
    refused = admit("decade_ops", data)
    if refused:
        return refused
    name = data.get("file")
    if name is None:
        return stamp("decade_ops", data, {"cli": CLI})
    if name not in CLI:
        return {"ok": False, "error": "unknown file", "card": "decade_ops", "cli": list(CLI)}
    return stamp("decade_ops", data, {"cli": CLI, "file": name})
