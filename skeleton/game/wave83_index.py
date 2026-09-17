"""Wave-83 census."""

from __future__ import annotations

from typing import Any


PACKS = ("pleach_pack", "hedgestake_pack", "binder_pack", "ether_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave83_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
