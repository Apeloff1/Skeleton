"""Wave-39 census."""

from __future__ import annotations

from typing import Any


PACKS = ("sextant_pack", "logchip_pack", "leadline_pack", "azimuth_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave39_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
