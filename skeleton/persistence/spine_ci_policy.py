"""Repository-owned required-check policy for P2 exact-head CI evidence."""

from __future__ import annotations

import hashlib
import json


REQUIRED_CHECK_WORKFLOWS = {
    "Backend Quality": ".github/workflows/backend-quality.yml",
    "P2 Repository Engineering Control": (
        ".github/workflows/p2-repository-engineering.yml"
    ),
    "Provider Surface Closure Gate": (
        ".github/workflows/provider-surface-closure.yml"
    ),
    "Repository Hygiene Gate": (
        ".github/workflows/repository-hygiene-gate.yml"
    ),
    "State Recovery Drill": ".github/workflows/state-recovery-drill.yml",
    "Workflow Input Security": (
        ".github/workflows/workflow-input-security.yml"
    ),
}
REQUIRED_CHECKS = tuple(sorted(REQUIRED_CHECK_WORKFLOWS))
REQUIRED_CHECK_EVENT = "pull_request"


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
        "schema_version": 2,
        "required_checks": [
            {
                "name": name,
                "workflow_path": REQUIRED_CHECK_WORKFLOWS[name],
                "event": REQUIRED_CHECK_EVENT,
            }
            for name in REQUIRED_CHECKS
        ],
    }
)


__all__ = [
    "REQUIRED_CHECKS",
    "REQUIRED_CHECK_EVENT",
    "REQUIRED_CHECK_POLICY_DIGEST",
    "REQUIRED_CHECK_WORKFLOWS",
]
