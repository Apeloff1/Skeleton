"""Wave-76 census."""

from __future__ import annotations

from typing import Any


PACKS = ("trellis_pack", "cane_pack", "must_pack", "lees_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave76_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
