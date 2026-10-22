"""skeleton/app/gap_ci.py
Complete CI verification script for the multi-gap starter packet.
Runs the probe and prints the health digest. Exits non-zero on failure.
"""
from __future__ import annotations

import json
import sys

from skeleton.app.gap_health import health_card
from skeleton.app.gap_probe import probe

def verify() -> int:
    """Run probe and emit digest. Return 0 only on success."""
    code = probe()
    if code != 0:
        print("probe failed", file=sys.stderr)
        return code
    card = health_card()
    print(json.dumps({"ci_ok": True, "digest": card["digest"], "stored_prose": 0}))
    return 0

if __name__ == "__main__":
    raise SystemExit(verify())
