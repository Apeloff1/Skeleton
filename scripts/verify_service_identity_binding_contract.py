#!/usr/bin/env python3
"""Repository contract verifier for G161 internal service identity binding.

Confirms the canonical owner, the byte-identical AI mirror, and that this
check does not claim enterprise or hostile-gap verification.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANON = ROOT / "skeleton/security/zero_trust.py"
MIRROR = ROOT / "skeleton/ai/runtime/security/zero_trust.py"
CONTRACT = ROOT / "machine/service_identity_binding_contract.json"


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("gap_id") != "G161":
        raise SystemExit("G161 contract identity mismatch")
    if contract.get("mirror_mode") != "byte_identical":
        raise SystemExit("G161 mirror must stay byte-identical")
    if contract.get("closure", {}).get("self_signing_forbidden") is not True:
        raise SystemExit("G161 contract must forbid self-signing")
    canon = CANON.read_text(encoding="utf-8")
    mirror = MIRROR.read_text(encoding="utf-8")
    if canon != mirror:
        raise SystemExit("G161 AI mirror drifted from the canonical owner")
    required = (
        "internal service identity is cryptographically bound",
        'kind": "internal_service_identity"',
        "identity_unbound",
        "identity_verifier_failed",
        "invalid prior decision",
    )
    missing = [marker for marker in required if marker not in canon]
    if missing:
        raise SystemExit(f"G161 authority markers missing: {missing}")
    print(
        json.dumps(
            {
                "gap_id": "G161",
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
