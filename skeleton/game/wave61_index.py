"""Wave-61 census."""

from __future__ import annotations

from typing import Any


PACKS = ("oxbow_pack", "yokebeam_pack", "yokepin_pack", "yokestaple_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave61_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
