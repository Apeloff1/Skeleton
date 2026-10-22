"""skeleton/app/gap_seal.py
Complete provenance seal for the multi-gap starter packet.
Hashes the readiness digest into a final card. Fail-closed.
"""
from __future__ import annotations

import hashlib
from typing import Any

from skeleton.app.gap_ready import readiness_declaration

def provenance_seal() -> dict[str, Any]:
    """Produce a seal card only after readiness succeeds."""
    ready = readiness_declaration()
    if not ready.get("ready"):
        raise RuntimeError("not ready")
    payload = f"{ready['digest']}:sealed"
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return {
        "kind": "gap_seal",
        "sealed": True,
        "digest": digest,
        "plane_count": ready["plane_count"],
        "stored_prose": 0,
    }

if __name__ == "__main__":
    import json
    print(json.dumps(provenance_seal(), indent=2))
