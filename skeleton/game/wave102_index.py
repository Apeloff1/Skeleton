"""Wave-102 census."""

from __future__ import annotations

from typing import Any


PACKS = ("pounce_pack", "oakgall_pack", "lampblack_pack", "quillcut_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave102_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
