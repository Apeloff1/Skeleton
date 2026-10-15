"""Onboarding flow — Pareto first-session teaching.

Teach the core verb in a safe space before any real gate.
"""

from __future__ import annotations

from typing import Any


def onboarding(title: str, core_verb: str = "use") -> dict[str, Any]:
    return {
        "title": title,
        "core_verb": core_verb,
        "steps": [
            "safe space with no fail state",
            "single clear affordance",
            "immediate rewarding feedback",
            "optional second example",
            "exit into first real (but clued) challenge",
        ],
        "rules": [
            "No soft-lock in onboarding",
            "No required external knowledge",
            "Text minimal and era-appropriate",
        ],
        "done_when": "Player has successfully used the core verb once without prompt",
    }
