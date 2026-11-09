"""Optional branches — Pareto side content that never blocks.

Rewards curiosity without creating soft-locks or required backtracking.
"""

from __future__ import annotations

from typing import Any


def optional_branch(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "rules": [
            "Clearly marked as optional (silhouette, color, or examine)",
            "Critical path completable if ignored",
            "Return path obvious",
            "Reward is mastery, lore, or shortcut — not a required key",
        ],
        "anti_pattern": "Hidden required item with no clue",
    }
