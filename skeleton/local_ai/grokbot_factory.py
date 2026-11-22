"""
Implement one Skeleton GB packet per run as GrokBot via Cursor. Compose organs, open a PR, never merge, never ask the principal.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

MODE = "implement_packet"


def process(data: dict) -> dict:
    refused = admit("grokbot_factory", data)
    if refused:
        return refused
    if data.get("merge") is True:
        return {
            "ok": False,
            "error": "factory does not merge",
            "card": "grokbot_factory",
            "mode": MODE,
        }
    if "mode" in data and data["mode"] != MODE:
        return {"ok": False, "error": "mode is pinned", "card": "grokbot_factory", "mode": MODE}
    return stamp("grokbot_factory", data, {"mode": MODE})
