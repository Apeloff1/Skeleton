"""Wave-85 census."""

from __future__ import annotations

from typing import Any


PACKS = ("stile_pack", "squeeze_pack", "wicket_pack", "sneck_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave85_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
