"""Wave-22 census."""

from __future__ import annotations

from typing import Any


PACKS = ("hemp_pack", "twist_pack", "coil_pack", "strand_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave22_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
