"""Shared immutable primitives for declarative Ubuntu host operations.

This layer validates data only. It intentionally owns no process, filesystem,
network, package-manager, or Supervisor/Secretary execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Sequence

MAX_TEXT = 4096
MAX_ARGV_ITEMS = 128
MAX_METADATA_ITEMS = 64
MAX_TAGS = 32
_ALLOWED_DESIRED_STATES = frozenset(
    {"present", "absent", "latest", "running", "stopped"}
)


def _clean(value: str) -> str:
    """Return canonical required text and reject coercion or ambiguous whitespace."""
    if type(value) is not str:
        raise TypeError("bounded text must be str")
    if not value or value != value.strip() or len(value) > MAX_TEXT or "\x00" in value:
        raise ValueError("invalid bounded text")
    return value


def _optional_text(value: str) -> str:
    """Validate optional text without converting non-string values."""
    if type(value) is not str:
        raise TypeError("optional bounded text must be str")
    if not value:
        return ""
    return _clean(value)


def _strict_bool(value: bool, *, field_name: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be bool")
    return value


def _clean_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    if type(tags) is not tuple:
        raise TypeError("tags must be tuple[str, ...]")
    if len(tags) > MAX_TAGS:
        raise ValueError("too many tags")
    cleaned = tuple(_clean(tag) for tag in tags)
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("duplicate tags")
    return cleaned


def _validate_policy_fields(
    *,
    identifier: str,
    desired: str,
    version: str,
    owner: str,
    mode: str,
    enabled: bool,
    restart: bool,
    tags: tuple[str, ...],
) -> None:
    _clean(identifier)
    _clean(desired)
    _optional_text(version)
    _clean(owner)
    _clean(mode)
    _strict_bool(enabled, field_name="enabled")
    _strict_bool(restart, field_name="restart")
    _clean_tags(tags)


def _policy_errors(
    desired: str,
    *,
    enabled: bool,
    restart: bool,
) -> tuple[str, ...]:
    desired = _clean(desired)
    _strict_bool(enabled, field_name="enabled")
    _strict_bool(restart, field_name="restart")
    errors: list[str] = []
    if desired not in _ALLOWED_DESIRED_STATES:
        errors.append("unsupported desired state")
    if enabled and desired == "absent":
        errors.append("absent resource cannot be enabled")
    if restart and desired in {"absent", "stopped"}:
        errors.append("restart conflicts with state")
    return tuple(errors)


@dataclass(frozen=True, slots=True)
class UbuntuAction:
    """One bounded declarative host action.

    argv is data, not shell text. The class intentionally exposes no execution
    method.
    """

    name: str
    argv: tuple[str, ...]
    reason: str
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        _clean(self.name)
        _clean(self.reason)
        if type(self.argv) is not tuple:
            raise TypeError("argv must be tuple[str, ...]")
        if not self.argv:
            raise ValueError("argv must be non-empty")
        if len(self.argv) > MAX_ARGV_ITEMS:
            raise ValueError("argv exceeds bounded item count")
        for item in self.argv:
            _clean(item)
        if type(self.timeout_seconds) is not int:
            raise TypeError("timeout_seconds must be int")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 3600:
            raise ValueError("timeout out of bounds")

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "argv": self.argv,
            "reason": self.reason,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True, slots=True)
class UbuntuPlan:
    """Immutable collection of declarative actions plus bounded metadata."""

    actions: tuple[UbuntuAction, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.actions) is not tuple:
            raise TypeError("actions must be tuple[UbuntuAction, ...]")
        for action in self.actions:
            if type(action) is not UbuntuAction:
                raise TypeError("plan actions must be UbuntuAction")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        if len(self.metadata) > MAX_METADATA_ITEMS:
            raise ValueError("too many metadata items")
        normalized: dict[str, str] = {}
        for key, value in self.metadata.items():
            clean_key = _clean(key)
            clean_value = _clean(value)
            if clean_key in normalized:
                raise ValueError("duplicate metadata key")
            normalized[clean_key] = clean_value
        object.__setattr__(self, "metadata", MappingProxyType(normalized))

    def append(self, action: UbuntuAction) -> "UbuntuPlan":
        if type(action) is not UbuntuAction:
            raise TypeError("action must be UbuntuAction")
        return UbuntuPlan(self.actions + (action,), self.metadata)

    def extend(self, actions: Sequence[UbuntuAction]) -> "UbuntuPlan":
        if isinstance(actions, (str, bytes, bytearray)):
            raise TypeError("actions must be a sequence of UbuntuAction")
        return UbuntuPlan(self.actions + tuple(actions), self.metadata)

    def names(self) -> tuple[str, ...]:
        return tuple(action.name for action in self.actions)


def validate_plan(plan: UbuntuPlan) -> tuple[str, ...]:
    if type(plan) is not UbuntuPlan:
        raise TypeError("plan must be UbuntuPlan")
    errors: list[str] = []
    seen: set[str] = set()
    for action in plan.actions:
        if action.name in seen:
            errors.append("duplicate action: " + action.name)
        seen.add(action.name)
    return tuple(errors)


def merge_plans(*plans: UbuntuPlan) -> UbuntuPlan:
    result = UbuntuPlan()
    for plan in plans:
        if type(plan) is not UbuntuPlan:
            raise TypeError("all plans must be UbuntuPlan")
        result = result.extend(plan.actions)
    errors = validate_plan(result)
    if errors:
        raise ValueError("; ".join(errors))
    return result


__all__ = [
    "MAX_ARGV_ITEMS",
    "MAX_METADATA_ITEMS",
    "MAX_TAGS",
    "MAX_TEXT",
    "UbuntuAction",
    "UbuntuPlan",
    "merge_plans",
    "validate_plan",
]
