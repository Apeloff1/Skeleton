"""Output validation for pipeline stages.

A pipeline is only as trustworthy as its validators. Each stage result
can register named validators that inspect the output and accumulate
problems; a stage either passes, warns, or fails the whole run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Tuple

from skeleton.kernel.errors import PipelineError


class ValidationIssueLevel(str, Enum):
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class Validator:
    name: str
    check: Callable[[Any], List[str]]
    level: ValidationIssueLevel = ValidationIssueLevel.ERROR


@dataclass
class ValidationIssue:
    stage: str
    validator: str
    level: ValidationIssueLevel
    message: str


@dataclass
class ValidationReport:
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.level is ValidationIssueLevel.ERROR for i in self.issues)

    def summary(self) -> Dict[str, int]:
        out: Dict[str, int] = {"warnings": 0, "errors": 0}
        for issue in self.issues:
            if issue.level is ValidationIssueLevel.ERROR:
                out["errors"] += 1
            else:
                out["warnings"] += 1
        return out


class StageValidatorRegistry:
    """Validators attached per stage; run() checks every produced output."""

    def __init__(self) -> None:
        self._by_stage: Dict[str, List[Validator]] = {}

    def attach(self, stage: str, validator: Validator) -> None:
        self._by_stage.setdefault(stage, []).append(validator)

    def validate_results(self, results: Tuple[Any, ...]) -> ValidationReport:
        report = ValidationReport()
        for result in results:
            validators = self._by_stage.get(result.stage, [])
            for validator in validators:
                for message in validator.check(result.output):
                    report.issues.append(
                        ValidationIssue(
                            stage=result.stage,
                            validator=validator.name,
                            level=validator.level,
                            message=message,
                        )
                    )
        return report
