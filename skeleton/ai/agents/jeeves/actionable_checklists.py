"""Actionable checklists — Pareto gates for design, adventure, and production.

Copy-paste ready. No runtime dependencies.
"""

from __future__ import annotations

DESIGN_REVIEW = [
    "3-5 pillars stated and non-negotiable",
    "Core verb has immediate feedback and fail state",
    "Critical path has no soft-lock",
    "Every puzzle has visible clue before it gates",
    "Era/hardware constraints listed and respected",
    "Asset provenance rule present",
]

ADVENTURE_FAIRNESS = [
    "Room graph connectivity reviewed",
    "Hotspots adequately sized or highlighted",
    "Inventory combinations enumerated",
    "Hint ladder (3 levels) on critical puzzles",
    "Dialogue sets/checks flags explicitly",
    "Save/flag model serializes",
]

PRODUCTION_GATE = [
    "Vertical slice defined and scoped",
    "Design bible section owners assigned",
    "Asset pipeline has style-lock milestone",
    "QA focus includes soft-lock and era violations",
    "Content-lock criteria written",
    "Rollback build identified",
]

UX_PASS = [
    "Critical info never obscured by UI",
    "Failure is readable (text/audio/visual)",
    "Input consistent with era",
    "No color-only clues",
    "Examine/use feedback instant",
]


def all_checklists() -> dict[str, list[str]]:
    return {
        "design_review": DESIGN_REVIEW,
        "adventure_fairness": ADVENTURE_FAIRNESS,
        "production_gate": PRODUCTION_GATE,
        "ux_pass": UX_PASS,
    }
