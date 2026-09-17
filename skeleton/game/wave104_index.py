"""Wave-104 census."""

from __future__ import annotations

from typing import Any


PACKS = ("boardcover_pack", "paste_pack", "calf_pack", "morocco_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave104_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
