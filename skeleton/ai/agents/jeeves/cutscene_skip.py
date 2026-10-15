"""Cutscene skip — Pareto player control.

Every non-interactive sequence can be skipped without losing required information.
"""

from __future__ import annotations

from typing import Any


def skip_rules() -> dict[str, Any]:
    return {
        "rules": [
            "Skip available after a short hold or second press",
            "Skip never soft-locks",
            "Required story beats are also available via examine or log",
            "First viewing may delay skip by one second to avoid accidents",
            "Skip returns to gameplay cleanly",
        ],
        "anti_pattern": "Unskippable cutscene that gates progress with unique info",
    }
