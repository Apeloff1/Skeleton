"""Replay and mastery value — Pareto reasons to return.

Optional depth that does not block the critical path.
"""

from __future__ import annotations

from typing import Any


def replay_hooks(title: str) -> dict[str, Any]:
    return {
        "title": title,
        "optional": [
            "alternate solutions that feel clever",
            "discoverable lore or examine depth",
            "mastery challenge with no required reward",
            "speed or restraint goals",
        ],
        "rules": [
            "Never required for critical path",
            "Clued or fairly discoverable",
            "No soft-lock if ignored",
        ],
        "measure": "Players who finish still find at least one reason to look again",
    }
