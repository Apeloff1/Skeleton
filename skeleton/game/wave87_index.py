"""Wave-87 census."""

from __future__ import annotations

from typing import Any


PACKS = ("ford_pack", "stepstone_pack", "clapper_pack", "packhorse_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave87_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
