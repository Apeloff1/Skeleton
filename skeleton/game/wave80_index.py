"""Wave-80 census."""

from __future__ import annotations

from typing import Any


PACKS = ("corkline_pack", "mesh_pack", "selvedge_pack", "sinker_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave80_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
