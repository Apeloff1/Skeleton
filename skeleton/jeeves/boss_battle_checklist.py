"""Boss battle readiness checklist — Pareto gate before a boss ships.

Covers intro, tells, phases, arena, openings, retry, and reward.
"""

from __future__ import annotations


def boss_battle_checklist() -> list[str]:
    return [
        "Intro is short, skippable, and deals no pre-control damage",
        "Each attack has a unique tell",
        "Tells are reactable on target hardware",
        "Phases change visibly and extend taught verbs",
        "Arena is readable with recovery space",
        "Punish windows exist and are clear",
        "Retry has minimal runback and fair resources",
        "Victory reward and exit are obvious",
        "No soft-lock",
        "Era constraints respected",
    ]
