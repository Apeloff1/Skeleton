"""skeleton/app/gap_probe.py
Complete readiness probe for the multi-gap starter packet.
Exits 0 only when health card reports ready. Suitable for container HEALTHCHECK.
"""
from __future__ import annotations

import sys

from skeleton.app.gap_health import health_card

def probe() -> int:
    """Return 0 if ready, 1 otherwise."""
    try:
        card = health_card()
        if card.get("ready") is True and card.get("plane_count") == 10:
            return 0
        return 1
    except Exception:
        return 1

if __name__ == "__main__":
    raise SystemExit(probe())
