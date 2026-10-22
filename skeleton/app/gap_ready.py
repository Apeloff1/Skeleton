"""skeleton/app/gap_ready.py
Complete production readiness declaration for the multi-gap starter packet.
Confirms e2e surface and emits a final digest. Fail-closed.
"""
from __future__ import annotations

import hashlib
from typing import Any

from skeleton.app.gap_evidence import evidence_card

def readiness_declaration() -> dict[str, Any]:
    """Produce a readiness card only after evidence succeeds."""
    evidence = evidence_card()
    if not evidence.get("ci_ok"):
        raise RuntimeError("evidence not ok")
    payload = f"{evidence['digest']}:ready"
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return {
        "kind": "gap_ready",
        "ready": True,
        "digest": digest,
        "plane_count": evidence["plane_count"],
        "stored_prose": 0,
    }

if __name__ == "__main__":
    import json
    print(json.dumps(readiness_declaration(), indent=2))
