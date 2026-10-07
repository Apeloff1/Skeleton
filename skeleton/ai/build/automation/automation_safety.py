"""Fail-closed operator controls for autonomous repository automation."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Mapping

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"", "0", "false", "no", "off"})
_REASON_LIMIT = 500
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class AutomationSafetyError(ValueError):
    """Raised when an operator safety control is malformed."""


@dataclass(frozen=True, slots=True)
class AutomationSafety:
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


def _flag(env: Mapping[str, str], name: str) -> bool:
    raw = env.get(name, "")
    if not isinstance(raw, str):
        raise AutomationSafetyError(f"{name} must be a string")
    value = raw.strip().casefold()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise AutomationSafetyError(
        f"{name} must be one of: 1/0, true/false, yes/no, on/off"
    )


def load_automation_safety(
    env: Mapping[str, str] | None = None,
) -> AutomationSafety:
    """Load emergency automation controls without silently accepting bad values."""

    source = os.environ if env is None else env
    paused = _flag(source, "SKELETON_AUTOMATION_PAUSED")
    quarantined = _flag(source, "SKELETON_AUTOMATION_QUARANTINED")
    raw_reason = source.get("SKELETON_AUTOMATION_HOLD_REASON", "")
    if not isinstance(raw_reason, str):
        raise AutomationSafetyError("SKELETON_AUTOMATION_HOLD_REASON must be a string")
    reason = raw_reason.strip()
    if len(reason) > _REASON_LIMIT:
        raise AutomationSafetyError("SKELETON_AUTOMATION_HOLD_REASON is too long")
    if _CONTROL_RE.search(reason):
        raise AutomationSafetyError(
            "SKELETON_AUTOMATION_HOLD_REASON contains control characters"
        )
    return AutomationSafety(paused=paused, quarantined=quarantined, reason=reason)
