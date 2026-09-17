"""Wave-24 census."""

from __future__ import annotations

from typing import Any


PACKS = ("rick_pack", "cord_pack", "coppice_pack", "faggot_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave24_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
