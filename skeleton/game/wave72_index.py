"""Wave-72 census."""

from __future__ import annotations

from typing import Any


PACKS = ("smokehouse_pack", "cure_pack", "flitch_pack", "gammon_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave72_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
