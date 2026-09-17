"""Wave-98 census."""

from __future__ import annotations

from typing import Any


PACKS = ("courtbench_pack", "bar_pack", "plea_pack", "writ_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave98_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
