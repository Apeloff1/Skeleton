"""Wave-28 census."""

from __future__ import annotations

from typing import Any


PACKS = ("lye_pack", "ash_pack", "tallow_pack", "cake_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave28_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
