"""Wave-103 census."""

from __future__ import annotations

from typing import Any


PACKS = ("kettlestitch_pack", "endband_pack", "headband_pack", "tailband_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave103_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
