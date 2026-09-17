"""Wave-42 census."""

from __future__ import annotations

from typing import Any


PACKS = ("keel_pack", "rib_pack", "garboard_pack", "strake_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave42_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
