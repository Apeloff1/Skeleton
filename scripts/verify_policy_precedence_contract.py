#!/usr/bin/env python3
"""Independent repository contract verifier for G131 policy precedence."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANON = ROOT / "skeleton/security/policy_precedence.py"
MIRROR = ROOT / "skeleton/ai/runtime/security/policy_precedence.py"
CONTRACT = ROOT / "machine/policy_precedence_contract.json"

def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("gap_id") != "G131":
        raise SystemExit("G131 contract identity mismatch")
    a = CANON.read_bytes()
    b = MIRROR.read_bytes()
    if a != b:
        raise SystemExit("G131 canonical/governed-AI mirror drift")
    text = a.decode("utf-8")
    required = (
        '"tenant": 10', '"operator": 20', '"developer": 30',
        '"system": 40', '"invariant": 50',
        'raise PolicyConflictError("no authoritative policy rule")',
        'raise PolicyConflictError("conflicting rules at equal authority")',
        "policy_digest=_digest(matched)",
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise SystemExit(f"G131 authority markers missing: {missing}")
    print(json.dumps({
        "gap_id": "G131",
        "valid": True,
        "canonical_mirror_sha256": hashlib.sha256(a).hexdigest(),
        "closure_claimed": False,
    }, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
