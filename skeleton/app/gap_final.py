"""skeleton/app/gap_final.py
Complete final status confirmation for the multi-gap starter packet.
Prints the seal digest and plane count. Fail-closed.
"""
from __future__ import annotations

import json

from skeleton.app.gap_seal import provenance_seal

def final_status() -> dict:
    """Produce the final confirmation card."""
    seal = provenance_seal()
    return {
        "kind": "gap_final",
        "sealed": seal["sealed"],
        "digest": seal["digest"],
        "plane_count": seal["plane_count"],
        "stored_prose": 0,
    }

if __name__ == "__main__":
    print(json.dumps(final_status(), indent=2))
