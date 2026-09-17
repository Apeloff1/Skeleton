"""Wave-71 census."""

from __future__ import annotations

from typing import Any


PACKS = ("cream_pack", "separator_pack", "buttermilk_pack", "rennet_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave71_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
