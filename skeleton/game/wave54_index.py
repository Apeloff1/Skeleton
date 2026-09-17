"""Wave-54 census."""

from __future__ import annotations

from typing import Any


PACKS = ("ward_pack", "tumbler_pack", "lockbit_pack", "lockbow_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave54_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
