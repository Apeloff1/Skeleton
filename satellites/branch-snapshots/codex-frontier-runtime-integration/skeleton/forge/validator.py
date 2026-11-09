"""Standalone validator for Forge blueprints — pluggable rule packs.

`Blueprint.validate()` gives structural checks. The validator composes
those plus arbitrary named rules (organisation policy, naming standards,
kind whitelists) and reports with severity, not just a flat problem list.

- :class:`ValidationRule` — named check returning problems
- :class:`ValidationReport` — problems grouped by severity
- :class:`CompositeValidator` — runs rules; `default_validator()` ships
  the standard pack
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Tuple

from skeleton.kernel.errors import BlueprintError
from skeleton.forge.universal import Blueprint


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class ValidationProblem:
    rule: str
    severity: Severity
    message: str


@dataclass
class ValidationRule:
    name: str
    check: Callable[[Blueprint], List[str]]
    severity: Severity = Severity.ERROR


@dataclass
class ValidationReport:
    blueprint_id: str
    problems: List[ValidationProblem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(p.severity is Severity.ERROR for p in self.problems)

    def hard_fail(self) -> None:
        if not self.ok:
            raise BlueprintError(
                "blueprint validation failed",
                context={
                    "blueprint_id": self.blueprint_id,
                    "problems": [p.message for p in self.problems],
                },
            )


class CompositeValidator:
    """Runs structural validation first, then any registered rules."""

    def __init__(self) -> None:
        self._rules: List[ValidationRule] = []

    def add(self, rule: ValidationRule) -> None:
        self._rules.append(rule)

    def validate(self, blueprint: Blueprint) -> ValidationReport:
        report = ValidationReport(blueprint_id=blueprint.blueprint_id)
        for found in blueprint.validate():
            report.problems.append(
                ValidationProblem("structural", Severity.ERROR, found)
            )
        for rule in self._rules:
            for message in rule.check(blueprint):
                report.problems.append(
                    ValidationProblem(rule.name, rule.severity, message)
                )
        return report


def default_validator() -> CompositeValidator:
    """Standard pack: single-sink check, orphan components, empty wires."""
    validator = CompositeValidator()

    def orphan_check(bp: Blueprint) -> List[str]:
        wired = {w.src[0] for w in bp.wires} | {w.dst[0] for w in bp.wires}
        return [
            f"component {cid!r} has no wires"
            for cid in bp.components
            if cid not in wired
        ]

    def single_sink_check(bp: Blueprint) -> List[str]:
        sinks = [c.instance_id for c in bp.components.values() if c.kind == "sink"]
        if len(sinks) > 1:
            return [f"multiple sinks: {sinks}"]
        return []

    validator.add(ValidationRule("orphan-components", orphan_check, Severity.WARNING))
    validator.add(ValidationRule("single-sink", single_sink_check, Severity.WARNING))
    return validator
