"""Wave-69 census."""

from __future__ import annotations

from typing import Any


PACKS = ("sickleblade_pack", "sicklehook_pack", "swath_pack", "stook_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave69_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
