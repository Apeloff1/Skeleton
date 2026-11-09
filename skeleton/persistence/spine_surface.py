"""Unread provider surface card.

Names the surfaces that are not claimed green. Does not query them.
"""

from __future__ import annotations

from typing import Any


class SpineSurface:
    """Record that provider-surface and PR Automation are unread."""

    def card(self) -> dict[str, Any]:
        return {
            "kind": "spine_surface",
            "hit": False,
            "law": "surface-not-claimed",
            "citation": "VOL-134",
            "provider_surface_green": False,
            "pr_automation_green": False,
            "live_motor": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
