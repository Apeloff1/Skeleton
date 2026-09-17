"""Wave-48 census."""

from __future__ import annotations

from typing import Any


PACKS = ("globe_pack", "chimney_pack", "oilpot_pack", "wicktrim_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave48_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
