"""Wave-47 census."""

from __future__ import annotations

from typing import Any


PACKS = ("bilge_pack", "strum_pack", "rosebox_pack", "limber_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave47_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
