"""Ubuntu host operations primitives for Skeleton.
Declarative, bounded planning objects for Ubuntu hosts. This module never executes
host commands; it produces inspectable plans for a separately authorized executor.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Mapping, Sequence
MAX_TEXT = 4096

def _clean(value: str) -> str:
    value = str(value).strip()
    if not value or len(value) > MAX_TEXT or "\x00" in value:
        raise ValueError("invalid bounded text")
    return value

@dataclass(frozen=True, slots=True)
class UbuntuAction:
    name: str
    argv: tuple[str, ...]
    reason: str
    timeout_seconds: int = 30
    def __post_init__(self) -> None:
        _clean(self.name); _clean(self.reason)
        if not self.argv: raise ValueError("argv must be non-empty")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 3600: raise ValueError("timeout out of bounds")
    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "argv": self.argv, "reason": self.reason, "timeout_seconds": self.timeout_seconds}

@dataclass(frozen=True, slots=True)
class UbuntuPlan:
    actions: tuple[UbuntuAction, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)
    def append(self, action: UbuntuAction) -> "UbuntuPlan":
        return UbuntuPlan(self.actions + (action,), dict(self.metadata))
    def extend(self, actions: Sequence[UbuntuAction]) -> "UbuntuPlan":
        return UbuntuPlan(self.actions + tuple(actions), dict(self.metadata))
    def names(self) -> tuple[str, ...]:
        return tuple(a.name for a in self.actions)

def validate_plan(plan: UbuntuPlan) -> tuple[str, ...]:
    errors=[]; seen=set()
    for action in plan.actions:
        if action.name in seen: errors.append("duplicate action: " + action.name)
        seen.add(action.name)
    return tuple(errors)

def merge_plans(*plans: UbuntuPlan) -> UbuntuPlan:
    result=UbuntuPlan()
    for plan in plans: result=result.extend(plan.actions)
    errors=validate_plan(result)
    if errors: raise ValueError("; ".join(errors))
    return result

__all__ = ["MAX_TEXT", "UbuntuAction", "UbuntuPlan", "validate_plan", "merge_plans"]
