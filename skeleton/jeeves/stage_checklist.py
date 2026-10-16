"""Stage readiness checklist — Pareto gate before a stage is approved.

Combines flow, pacing, landmarks, set pieces, rest, optionals, and transitions.
"""

from __future__ import annotations


def stage_checklist() -> list[str]:
    return [
        "Entry orients",
        "Critical path has no dead ends or soft-locks",
        "Every gate has a visible clue",
        "Intensity has releases",
        "At least one landmark near entry and exit",
        "Set piece is fair and strongly fed back",
        "Rest area after major high (or justified absence)",
        "Optional branches clearly optional",
        "Transition preserves state and orients",
        "Era constraints and provenance respected",
    ]
