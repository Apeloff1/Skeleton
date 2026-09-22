"""API request validation — minimal dict-schema checks without heavy deps.

FastAPI routes shouldn't deep-validate payloads ad hoc. A Validator
checks named fields against simple callables (``required``, ``type_is``,
``within``) and returns the problems, like forge's validator paints
blueprints.

- :class:`FieldRule` — field name + predicate + message
- :class:`RequestValidator` — runs rules against a payload mapping
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from skeleton.api.middleware import MiddlewareError


class ValidationError(MiddlewareError):
    code = "API.VALIDATION"
    http_status = 422


@dataclass(frozen=True)
class FieldRule:
    name: str
    predicate: Callable[[Any], bool]
    message: str
    required: bool = True


@dataclass
class ValidationIssue:
    field: str
    message: str

    def to_dict(self) -> Dict[str, str]:
        return {"field": self.field, "message": self.message}


class RequestValidator:
    """Group of FieldRules run against a payload dict."""

    def __init__(self, rules: Iterable[FieldRule]) -> None:
        self._rules = list(rules)

    def validate(self, payload: Mapping[str, Any]) -> Tuple[ValidationIssue, ...]:
        issues: List[ValidationIssue] = []
        for rule in self._rules:
            value = payload.get(rule.name)
            if value is None:
                if rule.required:
                    issues.append(ValidationIssue(field=rule.name, message="required"))
                continue
            if not rule.predicate(value):
                issues.append(ValidationIssue(field=rule.name, message=rule.message))
        return tuple(issues)

    def check_or_raise(self, payload: Mapping[str, Any]) -> None:
        issues = self.validate(payload)
        if issues:
            raise ValidationError(
                "validation failed",
                context={"issues": [i.to_dict() for i in issues]},
            )

    # convenience builders
    @staticmethod
    def type_is(type_: type, message: Optional[str] = None) -> Callable[[Any], bool]:
        return lambda value: isinstance(value, type_)

    @staticmethod
    def within(min_: float, max_: float) -> Callable[[Any], bool]:
        return lambda value: min_ <= value <= max_
