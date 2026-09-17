"""Wave-73 census."""

from __future__ import annotations

from typing import Any


PACKS = ("mash_pack", "wort_pack", "hops_pack", "sparge_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave73_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
