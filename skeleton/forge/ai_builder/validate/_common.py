from __future__ import annotations

from typing import Any, Mapping

from skeleton.forge.validator import Severity, ValidationProblem


def err(rule: str, message: str) -> ValidationProblem:
    return ValidationProblem(rule, Severity.ERROR, message)


def warn(rule: str, message: str) -> ValidationProblem:
    return ValidationProblem(rule, Severity.WARNING, message)


def items(plan: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    """List-of-mapping entries, tolerating a malformed plan (schema reports it)."""
    value = plan.get(key)
    return [x for x in value if isinstance(x, Mapping)] if isinstance(value, list) else []


def ids(plan: Mapping[str, Any], key: str) -> set[str]:
    return {x["id"] for x in items(plan, key) if isinstance(x.get("id"), str)}
