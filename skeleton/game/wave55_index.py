"""Wave-55 census."""

from __future__ import annotations

from typing import Any


PACKS = ("saggar_pack", "setter_pack", "kilnbat_pack", "prop_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave55_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
