"""Wave-77 census."""

from __future__ import annotations

from typing import Any


PACKS = ("graft_pack", "scion_pack", "rootstock_pack", "espalier_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave77_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
