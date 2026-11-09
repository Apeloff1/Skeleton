"""Boss retry — Pareto fair failure.

Death returns the player to a sensible point with the lesson intact.
"""

from __future__ import annotations

from typing import Any


def retry() -> dict[str, Any]:
    return {
        "rules": [
            "Checkpoint just before or at the arena",
            "No long unskippable runback",
            "Resources fair for another attempt",
            "Pattern knowledge carries over",
            "Failure feedback points at the missed tell",
        ],
    }
