"""Fail-closed schema evolution and mixed-version compatibility checks.

VOL-129/VOL-130 runtime authority.  The machine registries describe canonical
schemas and support windows; this module performs executable compatibility
qualification before a version can be promoted.

The checker is intentionally conservative.  Ambiguous schema shapes, unknown
compatibility modes, type changes, requiredness drift, enum drift, and
constraint changes are classified explicitly rather than silently accepted.
Breaking transitions require both a migration and rollback plan and a support
window containing the old and new versions.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


MODES = ("backward", "forward", "full", "none")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,191}$")


class SchemaEvolutionError(ValueError):
    """Schema evolution input or policy is malformed."""


def _id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise SchemaEvolutionError(f"{field} must be a canonical identifier")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SchemaEvolutionError(f"{field} must be a positive integer")
    return value


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SchemaEvolutionError("compatibility evidence must be canonical JSON") from exc
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class CompatibilityIssue:
    kind: str
    field: str
    detail: str
    severity: str
    direction: str

    def __post_init__(self) -> None:
        _id(self.kind, "kind")
        if not isinstance(self.field, str):
            raise SchemaEvolutionError("field must be a string")
        if not isinstance(self.detail, str) or not self.detail:
            raise SchemaEvolutionError("detail must be non-empty")
        if self.severity not in {"breaking", "warning"}:
            raise SchemaEvolutionError("unsupported issue severity")
        if self.direction not in {"backward", "forward", "both", "informational"}:
            raise SchemaEvolutionError("unsupported issue direction")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "field": self.field,
            "detail": self.detail,
            "severity": self.severity,
            "direction": self.direction,
        }


@dataclass(frozen=True, slots=True)
class VersionWindow:
    current_version: int
    supported_versions: tuple[int, ...]
    max_supported_versions: int = 2

    def __post_init__(self) -> None:
        current = _positive_int(self.current_version, "current_version")
        maximum = _positive_int(self.max_supported_versions, "max_supported_versions")
        versions = tuple(
            sorted({_positive_int(item, "supported_version") for item in self.supported_versions})
        )
        if not versions:
            raise SchemaEvolutionError("supported_versions must be non-empty")
        if current not in versions:
            raise SchemaEvolutionError("current_version must be supported")
        if len(versions) > maximum:
            raise SchemaEvolutionError("supported_versions exceeds support window")
        object.__setattr__(self, "current_version", current)
        object.__setattr__(self, "supported_versions", versions)
        object.__setattr__(self, "max_supported_versions", maximum)

    def supports(self, version: int) -> bool:
        return _positive_int(version, "version") in self.supported_versions

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_version": self.current_version,
            "supported_versions": list(self.supported_versions),
            "max_supported_versions": self.max_supported_versions,
        }


@dataclass(frozen=True, slots=True)
class EvolutionPlan:
    from_version: int
    to_version: int
    migration_id: str
    rollback_id: str
    reversible: bool = True

    def __post_init__(self) -> None:
        source = _positive_int(self.from_version, "from_version")
        target = _positive_int(self.to_version, "to_version")
        if target <= source:
            raise SchemaEvolutionError("to_version must exceed from_version")
        object.__setattr__(self, "from_version", source)
        object.__setattr__(self, "to_version", target)
        object.__setattr__(self, "migration_id", _id(self.migration_id, "migration_id"))
        object.__setattr__(self, "rollback_id", _id(self.rollback_id, "rollback_id"))
        if not isinstance(self.reversible, bool):
            raise SchemaEvolutionError("reversible must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_version": self.from_version,
            "to_version": self.to_version,
            "migration_id": self.migration_id,
            "rollback_id": self.rollback_id,
            "reversible": self.reversible,
        }


def _schema_parts(schema: Mapping[str, Any], label: str) -> tuple[dict[str, dict[str, Any]], set[str], bool | None]:
    if not isinstance(schema, Mapping):
        raise SchemaEvolutionError(f"{label} must be a mapping")
    raw_props = schema.get("properties", {})
    raw_required = schema.get("required", [])
    if not isinstance(raw_props, Mapping):
        raise SchemaEvolutionError(f"{label}.properties must be a mapping")
    if isinstance(raw_required, (str, bytes)) or not isinstance(raw_required, Sequence):
        raise SchemaEvolutionError(f"{label}.required must be a sequence")
    props: dict[str, dict[str, Any]] = {}
    for name, definition in raw_props.items():
        if not isinstance(name, str) or not name:
            raise SchemaEvolutionError(f"{label}.properties has invalid field name")
        if not isinstance(definition, Mapping):
            raise SchemaEvolutionError(f"{label}.{name} definition must be a mapping")
        props[name] = dict(definition)
    required: set[str] = set()
    for name in raw_required:
        if not isinstance(name, str) or name not in props:
            raise SchemaEvolutionError(f"{label}.required references unknown field {name!r}")
        if name in required:
            raise SchemaEvolutionError(f"{label}.required contains duplicate {name!r}")
        required.add(name)
    additional = schema.get("additionalProperties")
    if additional is not None and not isinstance(additional, bool):
        raise SchemaEvolutionError(f"{label}.additionalProperties must be boolean when present")
    return props, required, additional


def _type_token(definition: Mapping[str, Any]) -> object:
    value = definition.get("type")
    if isinstance(value, list):
        return tuple(sorted(value))
    return value


def _enum_set(definition: Mapping[str, Any]) -> set[Any] | None:
    value = definition.get("enum")
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise SchemaEvolutionError("enum must be a non-empty list")
    try:
        return set(json.dumps(item, sort_keys=True, allow_nan=False) for item in value)
    except (TypeError, ValueError) as exc:
        raise SchemaEvolutionError("enum values must be canonical JSON") from exc


def _numeric(definition: Mapping[str, Any], key: str) -> float | None:
    value = definition.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaEvolutionError(f"{key} must be numeric")
    return float(value)


def _integer(definition: Mapping[str, Any], key: str) -> int | None:
    value = definition.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SchemaEvolutionError(f"{key} must be a non-negative integer")
    return value


class SchemaEvolutionGuard:
    """Compatibility checker with explicit mixed-version promotion rules."""

    def __init__(self, mode: str = "backward"):
        if mode not in MODES:
            raise SchemaEvolutionError(f"unsupported compatibility mode: {mode}")
        self.mode = mode
        self._checks_run = 0
        self._blocked = 0

    def evaluate(
        self,
        old: Mapping[str, Any],
        new: Mapping[str, Any],
        *,
        mode: Optional[str] = None,
    ) -> tuple[CompatibilityIssue, ...]:
        active_mode = self.mode if mode is None else mode
        if active_mode not in MODES:
            raise SchemaEvolutionError(f"unsupported compatibility mode: {active_mode}")
        self._checks_run += 1
        if active_mode == "none":
            return ()

        old_props, old_required, old_additional = _schema_parts(old, "old")
        new_props, new_required, new_additional = _schema_parts(new, "new")
        issues: list[CompatibilityIssue] = []

        def add(kind: str, field: str, detail: str, direction: str) -> None:
            relevant = (
                active_mode == "full"
                or direction == "both"
                or direction == active_mode
            )
            issues.append(
                CompatibilityIssue(
                    kind=kind,
                    field=field,
                    detail=detail,
                    severity="breaking" if relevant else "warning",
                    direction=direction,
                )
            )

        for name in sorted(set(old_props) - set(new_props)):
            add(
                "removed_field",
                name,
                f"field {name!r} was removed",
                "backward",
            )
        for name in sorted(set(new_props) - set(old_props)):
            if name in new_required:
                add(
                    "new_required",
                    name,
                    f"new required field {name!r} is absent from old data",
                    "backward",
                )
            elif old_additional is False:
                add(
                    "new_optional_with_closed_old_reader",
                    name,
                    f"old readers reject newly added field {name!r}",
                    "forward",
                )

        for name in sorted(set(old_props) & set(new_props)):
            old_def = old_props[name]
            new_def = new_props[name]
            if _type_token(old_def) != _type_token(new_def):
                add(
                    "type_change",
                    name,
                    f"type changed from {_type_token(old_def)!r} to {_type_token(new_def)!r}",
                    "both",
                )

            if name not in old_required and name in new_required:
                add(
                    "requiredness_tightened",
                    name,
                    f"optional field {name!r} became required",
                    "backward",
                )
            if name in old_required and name not in new_required:
                add(
                    "requiredness_relaxed",
                    name,
                    f"required field {name!r} became optional",
                    "forward",
                )

            old_enum = _enum_set(old_def)
            new_enum = _enum_set(new_def)
            if old_enum is not None and new_enum is not None:
                if not old_enum <= new_enum:
                    add(
                        "enum_narrowed",
                        name,
                        f"enum for {name!r} removed previously valid values",
                        "backward",
                    )
                if not new_enum <= old_enum:
                    add(
                        "enum_widened",
                        name,
                        f"enum for {name!r} added values old readers may reject",
                        "forward",
                    )
            elif old_enum is None and new_enum is not None:
                add(
                    "enum_constraint_added",
                    name,
                    f"field {name!r} gained a closed enum constraint",
                    "backward",
                )
            elif old_enum is not None and new_enum is None:
                add(
                    "enum_constraint_removed",
                    name,
                    f"field {name!r} removed its closed enum constraint",
                    "forward",
                )

            for key, backward_tightens_when_greater in (
                ("minimum", True),
                ("exclusiveMinimum", True),
                ("minLength", True),
                ("minItems", True),
                ("maximum", False),
                ("exclusiveMaximum", False),
                ("maxLength", False),
                ("maxItems", False),
            ):
                old_value = (
                    _integer(old_def, key)
                    if key in {"minLength", "minItems", "maxLength", "maxItems"}
                    else _numeric(old_def, key)
                )
                new_value = (
                    _integer(new_def, key)
                    if key in {"minLength", "minItems", "maxLength", "maxItems"}
                    else _numeric(new_def, key)
                )
                if old_value == new_value:
                    continue
                if old_value is None and new_value is not None:
                    add(
                        "constraint_added",
                        name,
                        f"{key} constraint added to {name!r}",
                        "backward",
                    )
                    continue
                if old_value is not None and new_value is None:
                    add(
                        "constraint_removed",
                        name,
                        f"{key} constraint removed from {name!r}",
                        "forward",
                    )
                    continue
                assert old_value is not None and new_value is not None
                tightens = (
                    new_value > old_value
                    if backward_tightens_when_greater
                    else new_value < old_value
                )
                add(
                    "constraint_tightened" if tightens else "constraint_relaxed",
                    name,
                    f"{key} changed from {old_value} to {new_value}",
                    "backward" if tightens else "forward",
                )

        if old_additional is not False and new_additional is False:
            add(
                "unknown_fields_closed",
                "*",
                "new schema rejects fields previously admitted",
                "backward",
            )
        if old_additional is False and new_additional is not False:
            add(
                "unknown_fields_opened",
                "*",
                "new writers may emit fields old readers reject",
                "forward",
            )
        return tuple(issues)

    def check(
        self,
        old: Dict[str, Any],
        new: Dict[str, Any],
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        active_mode = self.mode if mode is None else mode
        issues = self.evaluate(old, new, mode=active_mode)
        breaking = [issue for issue in issues if issue.severity == "breaking"]
        compatible = not breaking
        if not compatible:
            self._blocked += 1
        return {
            "compatible": compatible,
            "mode": active_mode,
            "issues": [issue.to_dict() for issue in issues],
            "breaking_count": len(breaking),
            "suggestion": self._suggest(issues) if breaking else None,
        }

    def check_transition(
        self,
        old: Mapping[str, Any],
        new: Mapping[str, Any],
        *,
        from_version: int,
        to_version: int,
        window: VersionWindow,
        plan: EvolutionPlan | None = None,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        source = _positive_int(from_version, "from_version")
        target = _positive_int(to_version, "to_version")
        if target <= source:
            raise SchemaEvolutionError("to_version must exceed from_version")
        if window.current_version != target:
            raise SchemaEvolutionError("support window current_version must equal to_version")
        if not window.supports(target):
            raise SchemaEvolutionError("support window does not include target version")

        result = self.check(dict(old), dict(new), mode=mode)
        breaking = result["breaking_count"] > 0
        migration_required = breaking
        rollback_required = breaking
        plan_valid = False
        if plan is not None:
            plan_valid = (
                plan.from_version == source
                and plan.to_version == target
                and plan.reversible is True
            )
            if not plan_valid:
                raise SchemaEvolutionError(
                    "evolution plan must bind exact versions and be reversible"
                )

        old_supported = window.supports(source)
        eligible = old_supported and (
            result["compatible"]
            or (
                breaking
                and plan_valid
                and window.supports(target)
            )
        )
        decision = {
            **result,
            "from_version": source,
            "to_version": target,
            "support_window": window.to_dict(),
            "migration_required": migration_required,
            "rollback_required": rollback_required,
            "plan": plan.to_dict() if plan is not None else None,
            "old_version_supported": old_supported,
            "eligible_for_promotion": eligible,
        }
        decision["decision_digest"] = _canonical_digest(decision)
        return decision

    def qualify_transition(
        self,
        old: Mapping[str, Any],
        new: Mapping[str, Any],
        *,
        from_version: int,
        to_version: int,
        window: VersionWindow,
        plan: EvolutionPlan | None = None,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        decision = self.check_transition(
            old,
            new,
            from_version=from_version,
            to_version=to_version,
            window=window,
            plan=plan,
            mode=mode,
        )
        if not decision["eligible_for_promotion"]:
            raise SchemaEvolutionError(
                "schema transition is not eligible for promotion"
            )
        return decision

    def _suggest(self, issues: Iterable[CompatibilityIssue]) -> str:
        kinds = {issue.kind for issue in issues if issue.severity == "breaking"}
        suggestions: list[str] = []
        if kinds & {"removed_field", "requiredness_tightened"}:
            suggestions.append("retain/deprecate fields or migrate old records first")
        if kinds & {"new_required", "constraint_tightened", "enum_narrowed"}:
            suggestions.append("stage additive compatibility before enforcing tighter reads")
        if "type_change" in kinds:
            suggestions.append("introduce a versioned field/schema and explicit migration")
        if kinds & {"unknown_fields_closed", "new_optional_with_closed_old_reader"}:
            suggestions.append("preserve mixed-version reader compatibility")
        return "; ".join(suggestions) if suggestions else "review transition explicitly"

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "schema-evolution-card",
            "mode": self.mode,
            "checks_run": self._checks_run,
            "blocked": self._blocked,
        }


__all__ = [
    "MODES",
    "CompatibilityIssue",
    "EvolutionPlan",
    "SchemaEvolutionError",
    "SchemaEvolutionGuard",
    "VersionWindow",
]
