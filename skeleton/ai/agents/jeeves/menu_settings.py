"""Settings menu — Pareto essential options only.

Volume, controls reminder, and accessibility. No clutter.
"""

from __future__ import annotations

from typing import Any


def settings_set() -> dict[str, Any]:
    return {
        "essential": ["master volume", "music", "sfx", "controls hint"],
        "accessibility": ["reduced motion", "high contrast if supported"],
        "rules": [
            "Changes apply immediately or on confirm with preview",
            "Defaults are safe",
            "Reset to default exists",
            "Era-appropriate — no options the hardware cannot honor",
        ],
    }
