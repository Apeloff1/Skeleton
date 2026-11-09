"""Difficulty curve — Pareto pacing control.

Explicit early/mid/late intensity with recovery beats.
"""

from __future__ import annotations

from typing import Any


def difficulty_curve(
    title: str,
    early: str = "teach and reward",
    mid: str = "complicate and combine",
    late: str = "express mastery under pressure",
) -> dict[str, Any]:
    return {
        "title": title,
        "early": early,
        "mid": mid,
        "late": late,
        "recovery_beats": "Insert lower-intensity moments after spikes",
        "anti_patterns": [
            "unannounced spike",
            "flat line with no new verb",
            "punishing fail with no readable feedback",
        ],
        "measure": "Playtest notes on hesitation and retry emotion",
    }


def spike_check() -> list[str]:
    return [
        "Is the new demand taught or clued?",
        "Is failure readable?",
        "Is there a recovery beat after?",
        "Does success feel earned?",
    ]
