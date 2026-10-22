"""skeleton/app/gap_evidence.py
Complete evidence card for the multi-gap starter packet.
Runs CI verify and records the digest. Fail-closed.
"""
from __future__ import annotations

from typing import Any

from skeleton.app.gap_ci import verify
from skeleton.app.gap_health import health_card

def evidence_card() -> dict[str, Any]:
    """Produce an evidence card only if CI verify succeeds."""
    code = verify()
    if code != 0:
        raise RuntimeError("CI verify failed")
    card = health_card()
    return {
        "kind": "gap_evidence",
        "ci_ok": True,
        "digest": card["digest"],
        "plane_count": card["plane_count"],
        "stored_prose": 0,
    }

if __name__ == "__main__":
    import json
    print(json.dumps(evidence_card(), indent=2))
