"""Wave-95 census."""

from __future__ import annotations

from typing import Any


PACKS = ("bushel_pack", "peck_pack", "gallon_pack", "firkin_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave95_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
