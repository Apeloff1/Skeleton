"""Enemy readiness checklist — Pareto gate before an enemy or encounter ships.

Covers telegraph, readability, behavior, fairness, placement, and bosses.
"""

from __future__ import annotations


def enemy_checklist() -> list[str]:
    return [
        "Unique readable silhouette",
        "States (idle/alert/act) are distinct",
        "Dangerous actions telegraph",
        "Reactable on target hardware",
        "Behavior transitions are visible",
        "First encounter teaches",
        "Damage avoidable after teach",
        "Placement supports stage flow; rests stay safe",
        "Bosses reuse taught verbs and have fair retry",
        "Era palette/sprite budget respected",
    ]
