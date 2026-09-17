"""Wave-16 census."""

from __future__ import annotations

from typing import Any


PACKS = ("well_pack", "pump_pack", "cistern_pack", "sluice_pack", "weir_pack", "channel_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave16_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
