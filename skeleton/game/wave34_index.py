"""Wave-34 census."""

from __future__ import annotations

from typing import Any


PACKS = ("batten_pack", "nib_pack", "ridge_pack", "valley_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave34_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
