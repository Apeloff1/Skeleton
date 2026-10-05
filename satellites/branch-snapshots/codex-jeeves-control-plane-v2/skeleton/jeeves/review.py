"""Jeeves code review — static, explainable findings.

The tutor endpoint accepts a snippet and returns structured findings
with explainable rules: naming, complexity proxies, dead imports, and
style heuristics. Findings carry severity so the API can sort them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Tuple

from skeleton.kernel.errors import KernelError


class ReviewError(KernelError):
    code = "JEE.REVIEW"


class FindingSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: FindingSeverity
    message: str
    line: int


@dataclass(frozen=True)
class ReviewRule:
    name: str
    check: Callable[[str], List[Finding]]
    severity: FindingSeverity = FindingSeverity.WARNING


class CodeReviewer:
    """Runs registered rules and returns findings sorted by line."""

    def __init__(self) -> None:
        self._rules: List[ReviewRule] = []

    def register(self, rule: ReviewRule) -> None:
        self._rules.append(rule)

    def review(self, code: str) -> Tuple[Finding, ...]:
        findings: List[Finding] = []
        for rule in self._rules:
            findings.extend(rule.check(code))
        return tuple(sorted(findings, key=lambda f: (f.line, f.rule)))


def default_reviewer() -> CodeReviewer:
    reviewer = CodeReviewer()

    def long_line_check(code: str) -> List[Finding]:
        out: List[Finding] = []
        for idx, line in enumerate(code.splitlines(), start=1):
            if len(line) > 120:
                out.append(
                    Finding("long-line", FindingSeverity.WARNING, "over 120 chars", idx)
                )
        return out

    def todo_check(code: str) -> List[Finding]:
        out: List[Finding] = []
        for idx, line in enumerate(code.splitlines(), start=1):
            if "TODO" in line or "FIXME" in line:
                out.append(
                    Finding("todo-marker", FindingSeverity.INFO, "unresolved marker", idx)
                )
        return out

    reviewer.register(ReviewRule("long-line", long_line_check, FindingSeverity.WARNING))
    reviewer.register(ReviewRule("todo-marker", todo_check, FindingSeverity.INFO))
    return reviewer
