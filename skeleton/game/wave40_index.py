"""Wave-40 census."""

from __future__ import annotations

from typing import Any


PACKS = ("boltrope_pack", "cringle_pack", "reef_pack", "grommet_pack")


def census() -> dict[str, Any]:
    return {"kind": "wave40_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
