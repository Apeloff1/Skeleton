"""Menu feedback — Pareto immediate response to every input.

Focus move, confirm, and cancel all produce a signal.
"""

from __future__ import annotations

from typing import Any


def feedback() -> dict[str, Any]:
    return {
        "signals": ["focus change", "confirm", "cancel", "invalid", "value change"],
        "rules": [
            "Visual change on focus",
            "Audio tick if budget allows",
            "Invalid explains why",
            "No silent ignore",
            "Latency within a frame or two",
        ],
    }
