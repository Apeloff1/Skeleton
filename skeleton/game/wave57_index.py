"""Wave-57 census."""

from __future__ import annotations

from typing import Any


PACKS = ("saddletree_pack", "pommel_pack", "cantle_pack", "stirrup_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave57_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
