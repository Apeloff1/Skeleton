"""Wave-10 census."""

from __future__ import annotations

from typing import Any


PACKS = (
    "folio_pack", "shelf_pack", "slip_pack", "stack_pack", "bind_pack",
    "callno_pack", "loan_pack", "hold_pack", "fine_pack",
)


def census() -> dict[str, Any]:
    return {"kind": "wave10_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
