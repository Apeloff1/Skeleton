"""Wave-7 census."""

from __future__ import annotations

from typing import Any


PACKS = (
    "sched_pack", "ticket_pack", "locker_pack", "punch_pack", "uniform_pack", "inspect_pack",
    "cite_pack", "waiver_pack", "custody_pack", "evidence_pack", "grate_pack", "flue_pack",
    "damper_pack", "ember_pack", "soot_pack", "clinker_pack", "firebox_pack", "draft_pack",
    "ashpan_pack", "chimney_pack", "oil_pack", "compass_pack", "sheet_pack", "dock_pack",
    "ballast_pack", "keel_pack", "tide_pack", "silt_pack", "barnacle_pack", "tidelock_pack",
    "form_pack", "roster_pack", "brief_pack",
)


def census() -> dict[str, Any]:
    return {"kind": "wave7_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
