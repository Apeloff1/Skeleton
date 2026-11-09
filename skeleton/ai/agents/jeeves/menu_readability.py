"""Menu readability — Pareto contrast and type for era hardware.

Text and focus must read at native resolution.
"""

from __future__ import annotations

from typing import Any


def readability(era: str = "16bit") -> dict[str, Any]:
    return {
        "era": era,
        "rules": [
            "High contrast text on background",
            "Focus state unmistakable (not color-only)",
            "Short labels",
            "No essential info in tiny type",
            "Works in the era palette",
        ],
        "test": "Readable at 1x on target core or reference",
    }
