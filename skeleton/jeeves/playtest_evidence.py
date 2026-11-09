"""Playtest and evidence protocol — Pareto validation for design claims.

Structured notes only. No native execution in this layer.
"""

from __future__ import annotations

from typing import Any


def playtest_session(
    title: str,
    focus: str = "critical path",
    build_id: str = "vertical-slice",
) -> dict[str, Any]:
    return {
        "title": title,
        "build_id": build_id,
        "focus": focus,
        "observer_notes": [
            "Where did the player hesitate?",
            "Was the clue found before the gate?",
            "Was failure readable?",
            "Did any soft-lock occur?",
            "Which verb felt unclear?",
        ],
        "evidence_to_capture": [
            "timestamped notes",
            "flag/inventory state at stuck points",
            "screenshot or description of fail feedback",
        ],
        "decision": "approve slice | revise clue/feedback | cut scope",
    }


def evidence_bar() -> list[str]:
    return [
        "Claim of fairness supported by at least one observed play",
        "Critical path completed without external guide",
        "Era constraints not violated in the tested segment",
        "Operator signs the session note before phase advance",
    ]
