"""Contextual prompts — Pareto verb hints that appear only when useful.

Show the available action near the hotspot, then get out of the way.
"""

from __future__ import annotations

from typing import Any


def prompt_spec() -> dict[str, Any]:
    return {
        "when": "Player is near an interactive and the verb is not yet mastered",
        "content": "Short verb name or icon",
        "rules": [
            "Does not cover the hotspot",
            "Fades once the verb is used successfully nearby",
            "Never required reading for critical path after teach",
            "Era-readable size",
        ],
    }
