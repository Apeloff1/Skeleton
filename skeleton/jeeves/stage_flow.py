"""Stage flow — Pareto connectivity and pacing for a single stage.

Defines entry, beats, gates, and exit so a stage reads as one coherent unit.
"""

from __future__ import annotations

from typing import Any


def stage_flow(title: str, beats: int = 5) -> dict[str, Any]:
    return {
        "title": title,
        "structure": ["entry", "teach_or_setup", "complication", "climax_or_gate", "resolution_or_exit"],
        "beats": beats,
        "rules": [
            "Entry orients the player",
            "Each gate has a visible clue before it",
            "Intensity rises then releases",
            "Exit clearly signals completion",
        ],
        "connectivity": "Linear with optional branches; no dead ends on critical path",
    }
