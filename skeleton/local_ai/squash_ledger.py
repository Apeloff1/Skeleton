"""
Local squash1 ledger pattern. Merkle notes, SQUASH.md, no remote create when 403.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

LEDGER = "squash1"


def process(data: dict) -> dict:
    refused = admit("squash_ledger", data)
    if refused:
        return refused
    if data.get("remote") is True:
        return {
            "ok": False,
            "error": "ledger stays local",
            "card": "squash_ledger",
            "ledger": LEDGER,
        }
    return stamp("squash_ledger", data, {"ledger": LEDGER})
