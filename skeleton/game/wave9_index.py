"""Wave-9 census."""

from __future__ import annotations

from typing import Any


PACKS = (
    "strut_pack", "truss_pack", "rivet_pack", "gusset_pack", "span_pack", "pier_pack",
    "abutment_pack", "deck_pack", "rail_pack", "sleeper_pack", "switch_pack", "signal_pack",
    "couple_pack", "buffer_pack", "lattice_pack", "bolt_pack", "plate_pack", "brace_pack",
    "load_pack", "survey_pack", "grade_pack", "align_pack", "joint_pack", "wind_pack",
)


def census() -> dict[str, Any]:
    return {"kind": "wave9_census", "n": len(PACKS), "packs": list(PACKS), "sota_ready": False, "stored_prose": 0}
