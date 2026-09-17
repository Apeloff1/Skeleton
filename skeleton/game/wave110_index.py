"""Wave-110 census."""

from __future__ import annotations

from typing import Any


PACKS = ("registry_pack", "enrolment_pack", "calendaroll_pack", "memorial_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave110_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
