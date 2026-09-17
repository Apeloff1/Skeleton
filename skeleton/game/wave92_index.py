"""Wave-92 census."""

from __future__ import annotations

from typing import Any


PACKS = ("coindie_pack", "planchet_pack", "coincollar_pack", "reededge_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave92_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
