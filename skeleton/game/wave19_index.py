"""Wave-19 census."""

from __future__ import annotations

from typing import Any


PACKS = ("mill_pack", "hopper_pack", "sack_pack", "flour_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave19_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
