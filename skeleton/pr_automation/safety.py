"""Operator emergency controls for privileged PR automation.

The PR automation workflow intentionally stages only the trusted
`skeleton/pr_automation` package into an isolated Python path. This module is
therefore self-contained rather than importing broader repository automation
code. Its semantics mirror the repository-wide automation safety contract:
malformed controls fail closed, quarantine dominates pause, and a hold can be
checked before credentials or network clients are constructed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Mapping

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"", "0", "false", "no", "off"})
_REASON_LIMIT = 500
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class OperatorSafetyError(ValueError):
    """Raised when emergency automation controls are malformed."""


@dataclass(frozen=True, slots=True)
class OperatorSafety:
    paused: bool
    quarantined: bool
    reason: str = ""

    @property
    def blocked(self) -> bool:
        return self.paused or self.quarantined

    @property
    def status(self) -> str:
        if self.quarantined:
            return "quarantined"
        if self.paused:
            return "paused"
        return "active"

    def public_payload(self) -> dict[str, object]:
        """Return bounded non-secret state suitable for workflow diagnostics."""

        return {
            "status": self.status,
            "blocked": self.blocked,
            "reason": self.reason,
        }


def _flag(source: Mapping[str, str], name: str) -> bool:
    raw = source.get(name, "")
    if not isinstance(raw, str):
        raise OperatorSafetyError(f"{name} must be a string")
    normalized = raw.strip().casefold()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    raise OperatorSafetyError(
        f"{name} must be one of: 1/0, true/false, yes/no, on/off"
    )


def load_operator_safety(
    env: Mapping[str, str] | None = None,
) -> OperatorSafety:
    """Load emergency controls and reject ambiguous values.

    Controls are configuration authority. Silently treating an unknown value
    as false would turn a typo in an incident-response kill switch into a
    fail-open condition, so malformed values raise before automation begins.
    """

    source = os.environ if env is None else env
    paused = _flag(source, "SKELETON_AUTOMATION_PAUSED")
    quarantined = _flag(source, "SKELETON_AUTOMATION_QUARANTINED")
    raw_reason = source.get("SKELETON_AUTOMATION_HOLD_REASON", "")
    if not isinstance(raw_reason, str):
        raise OperatorSafetyError(
            "SKELETON_AUTOMATION_HOLD_REASON must be a string"
        )
    reason = raw_reason.strip()
    if len(reason) > _REASON_LIMIT:
        raise OperatorSafetyError(
            "SKELETON_AUTOMATION_HOLD_REASON is too long"
        )
    if _CONTROL_RE.search(reason):
        raise OperatorSafetyError(
            "SKELETON_AUTOMATION_HOLD_REASON contains control characters"
        )
    return OperatorSafety(
        paused=paused,
        quarantined=quarantined,
        reason=reason,
    )


__all__ = [
    "OperatorSafety",
    "OperatorSafetyError",
    "load_operator_safety",
]
