"""Wave-38 census."""

from __future__ import annotations

from typing import Any


PACKS = ("chain_pack", "rod_pack", "staff_pack", "theo_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave38_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
