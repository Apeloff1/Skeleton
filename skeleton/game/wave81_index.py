"""Wave-81 census."""

from __future__ import annotations

from typing import Any


PACKS = ("dredge_pack", "tongs_pack", "oysterrake_pack", "shellbed_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave81_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
