"""
ACE fail-close for local AI. Align with PR 87. Secret scan. No live secrets.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

FORBIDDEN = [".env", "token", "pem", "secret"]


def scan(path: str) -> bool:
    if not isinstance(path, str) or not path or len(path) > 240:
        return False
    if ".." in path or path.startswith(("/", "\\")) or any(ord(ch) < 32 for ch in path):
        return False
    lowered = path.lower()
    return not any(flag in lowered for flag in FORBIDDEN)


def process(data: dict) -> dict:
    refused = admit("security_ace", data)
    if refused:
        return refused
    path = data.get("path")
    if path is None:
        return stamp("security_ace", data, {"forbidden": FORBIDDEN})
    if not scan(path):
        return {
            "ok": False,
            "error": "path is forbidden",
            "card": "security_ace",
            "forbidden": list(FORBIDDEN),
        }
    return stamp("security_ace", data, {"forbidden": FORBIDDEN, "path": path})
