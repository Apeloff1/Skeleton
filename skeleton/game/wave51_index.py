"""Wave-51 census."""

from __future__ import annotations

from typing import Any


PACKS = ("millstone_pack", "shoe_pack", "damsel_pack", "tun_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave51_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
