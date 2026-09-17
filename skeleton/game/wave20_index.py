"""Wave-20 census."""

from __future__ import annotations

from typing import Any


PACKS = ("churn_pack", "curd_pack", "whey_pack", "cheese_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave20_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
