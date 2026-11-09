#!/usr/bin/env python3
"""Repository contract verifier for G084 trust-root recovery.

Confirms the canonical owner, the non-owning AI facade, and that this check
does not claim enterprise or hostile-gap verification.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANON = ROOT / "skeleton/security/trust_root_recovery.py"
MIRROR = ROOT / "skeleton/ai/runtime/security/trust_root_recovery.py"
CONTRACT = ROOT / "machine/trust_root_recovery_contract.json"
REQUIRED_IMPORT = "from skeleton.security.trust_root_recovery import"


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("gap_id") != "G084":
        raise SystemExit("G084 contract identity mismatch")
    if contract.get("closure", {}).get("self_signing_forbidden") is not True:
        raise SystemExit("G084 contract must forbid self-signing")
    canon = CANON.read_text(encoding="utf-8")
    mirror = MIRROR.read_text(encoding="utf-8")
    if canon == mirror:
        raise SystemExit("G084 AI mirror must be a facade, not a second owner")
    if REQUIRED_IMPORT not in mirror:
        raise SystemExit("G084 facade missing canonical import")
    required = (
        "successor appointment is immutable",
        "revocation requires a precommitted successor",
        "verifier key does not match authority",
        "trust cut must precede revocation",
        "re-sign requires one pre-cut admission from a revoked root",
        'kind": "root_revocation"',
        'kind": "artifact_resign"',
    )
    missing = [marker for marker in required if marker not in canon]
    if missing:
        raise SystemExit(f"G084 authority markers missing: {missing}")
    print(
        json.dumps(
            {
                "gap_id": "G084",
                "valid": True,
                "canonical_sha256": hashlib.sha256(canon.encode("utf-8")).hexdigest(),
                "closure_claimed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
