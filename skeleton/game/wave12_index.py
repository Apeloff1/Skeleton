"""Wave-12 census."""

from __future__ import annotations

from typing import Any


PACKS = ("graft_pack", "prune_pack", "harvest_pack", "cellar_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave12_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
