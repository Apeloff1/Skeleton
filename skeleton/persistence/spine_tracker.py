"""Completion tracker for the P2 spine.

Percentages are reads of what is landed. They are not a completion checkbox.
"""

from __future__ import annotations

from typing import Any


class SpineTracker:
    """Report landed surface versus the still-open seams."""

    def card(self) -> dict[str, Any]:
        return {
            "kind": "spine_tracker",
            "hit": False,
            "law": "percent-is-not-signoff",
            "citation": "VOL-134",
            "read_project_percent": 84,
            "apply_percent": 0,
            "motor_bootstrap_percent": 0,
            "ci_green_percent": 0,
            "merge_percent": 0,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
