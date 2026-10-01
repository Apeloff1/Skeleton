"""Repository-owned required-check policy for P2 exact-head CI evidence."""

from __future__ import annotations

import hashlib
import json


REQUIRED_CHECKS = (
    "Backend Quality",
    "P2 Repository Engineering Control",
    "Provider Surface Closure Gate",
    "Repository Hygiene Gate",
    "State Recovery Drill",
    "Workflow Input Security",
)


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


REQUIRED_CHECK_POLICY_DIGEST = _digest(
    {
        "schema_version": 1,
        "required_checks": list(REQUIRED_CHECKS),
    }
)


__all__ = ["REQUIRED_CHECKS", "REQUIRED_CHECK_POLICY_DIGEST"]
