"""Wave-41 census."""

from __future__ import annotations

from typing import Any


PACKS = ("sheave_pack", "tackle_pack", "stayline_pack", "shroud_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave41_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
