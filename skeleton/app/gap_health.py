"""skeleton/app/gap_health.py
Complete health card for the multi-gap starter packet.
Aggregates status and emits a readiness receipt. Fail-closed.
"""
from __future__ import annotations

import hashlib
from typing import Any

from skeleton.app.gap_status import generate_status

try:
    from skeleton.provenance.chronicle import emit_receipt
except ImportError:
    def emit_receipt(**kwargs):
        return kwargs.get("digest", "")

def health_card() -> dict[str, Any]:
    """Produce a readiness card. Ready only if all 10 planes report."""
    status = generate_status()
    ready = status.get("plane_count") == 10 and status.get("ready") is True
    payload = f"{status['digest']}:{ready}"
    digest = hashlib.sha256(payload.encode()).hexdigest()
    emit_receipt(kind="gap_health", digest=digest, ready=ready, stored_prose=0)
    return {
        "kind": "gap_health",
        "ready": ready,
        "digest": digest,
        "plane_count": status.get("plane_count", 0),
        "stored_prose": 0,
    }

if __name__ == "__main__":
    import json
    print(json.dumps(health_card(), indent=2))
