"""Wave-78 census."""

from __future__ import annotations

from typing import Any


PACKS = ("brood_pack", "supers_pack", "queen_pack", "smoker_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave78_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
