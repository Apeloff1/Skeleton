"""Wave-99 census."""

from __future__ import annotations

from typing import Any


PACKS = ("poll_pack", "tithe_pack", "hideacre_pack", "geld_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave99_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
