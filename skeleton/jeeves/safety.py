"""Tutor input guard — flag blocked patterns before assessment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple

from skeleton.kernel.errors import JeevesError


class SafetyError(JeevesError):
    code = "JEE.SAFETY"


class SafetyLevel(str, Enum):
    ALLOW = "ALLOW"
    FLAG = "FLAG"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class SafetyFlag:
    rule: str
    level: SafetyLevel
    matched: str


class SafetyGuard:
    """Block obvious-secret patterns; adopt more rules via register()."""

    BLOCKED_PATTERNS = [
        r"api[_-]?key",
        r"password\s*=",
        r"BEGIN PRIVATE KEY",
    ]

    def __init__(self) -> None:
        self._blocked = [
            re.compile(p, re.IGNORECASE) for p in self.BLOCKED_PATTERNS
        ]

    def register(self, pattern: str) -> None:
        self._blocked.append(re.compile(pattern, re.IGNORECASE))

    def check(self, text: str) -> Tuple[SafetyFlag, ...]:
        findings = []
        for pattern in self._blocked:
            match = pattern.search(text)
            if match:
                findings.append(
                    SafetyFlag(
                        rule="blocked-pattern",
                        level=SafetyLevel.BLOCK,
                        matched=match.group(0)[:40],
                    )
                )
        return tuple(findings)

    def guard(self, text: str) -> None:
        findings = self.check(text)
        if any(f.level is SafetyLevel.BLOCK for f in findings):
            raise SafetyError(
                "blocked content",
                context={"rules": [f.rule for f in findings]},
            )
