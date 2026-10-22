"""skeleton/app/gap_metrics.py
Complete metrics summary for the multi-gap starter packet.
Reports plane count, readiness, and digest. Fail-closed.
"""
from __future__ import annotations

from typing import Any

from skeleton.app.gap_health import health_card

def metrics_summary() -> dict[str, Any]:
    """Produce a metrics card from the health aggregator."""
    health = health_card()
    return {
        "kind": "gap_metrics",
        "ready": health["ready"],
        "plane_count": health["plane_count"],
        "digest": health["digest"],
        "stored_prose": 0,
    }

if __name__ == "__main__":
    import json
    print(json.dumps(metrics_summary(), indent=2))
