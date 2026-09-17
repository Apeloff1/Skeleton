"""Wave-82 census."""

from __future__ import annotations

from typing import Any


PACKS = ("peatcut_pack", "slane_pack", "peatbank_pack", "peatstack_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave82_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
