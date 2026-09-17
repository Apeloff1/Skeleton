"""Wave-65 census."""

from __future__ import annotations

from typing import Any


PACKS = ("winnowfan_pack", "winnowsieve_pack", "chaff_pack", "winnowbasket_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave65_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
