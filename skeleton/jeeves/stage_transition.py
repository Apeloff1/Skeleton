"""Stage transitions — Pareto handoff between stages.

Clear completion, brief orientation, no lost progress.
"""

from __future__ import annotations

from typing import Any


def transition(from_stage: str, to_stage: str) -> dict[str, Any]:
    return {
        "from": from_stage,
        "to": to_stage,
        "includes": [
            "Explicit completion signal",
            "Short orientation or landmark on arrival",
            "Flags and inventory preserved",
            "No required knowledge that was not taught",
        ],
        "avoid": ["abrupt hard cut with no feedback", "progress reset", "unclued new verb"],
    }
