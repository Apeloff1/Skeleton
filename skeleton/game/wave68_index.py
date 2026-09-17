"""Wave-68 census."""

from __future__ import annotations

from typing import Any


PACKS = ("seedlip_pack", "dibble_pack", "drillrow_pack", "rowmark_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave68_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
