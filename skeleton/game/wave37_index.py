"""Wave-37 census."""

from __future__ import annotations

from typing import Any


PACKS = ("escape_pack", "verge_pack", "fusee_pack", "pendulum_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave37_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
