"""Wave-111 census."""

from __future__ import annotations

from typing import Any


PACKS = ("piperoll_pack", "closeroll_pack", "patentroll_pack", "fineroll_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave111_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
