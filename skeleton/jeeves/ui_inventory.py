"""Inventory UI — Pareto clear item state and combine.

Examine, select, and combine without hiding the world longer than needed.
"""

from __future__ import annotations

from typing import Any


def inventory_ui() -> dict[str, Any]:
    return {
        "shows": ["icon", "name", "selected state", "key examine line"],
        "rules": [
            "Open and close is instant and reversible",
            "Selected item obvious",
            "Combine is explicit, not free-parse",
            "Does not soft-lock if closed",
            "Era-readable icons",
        ],
    }
