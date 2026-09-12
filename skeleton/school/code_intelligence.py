"""Provider-agnostic code-intelligence policies mined from Tutolage.

This module deliberately contains deterministic analysis contracts rather than
model/provider plumbing. A future Jeeves adapter can attach semantic search,
LLM generation, compilers, and repository tools to these contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Iterable, Sequence


class CodeSignalKind(str, Enum):
    BUG_RISK = "bug_risk"
    SECURITY = "security"
    COMPLEXITY = "complexity"
    TEST_GAP = "test_gap"
    DOCUMENTATION = "documentation"
    ARCHITECTURE = "architecture"


class CodeTaskKind(str, Enum):
    SEARCH = "search"
    REVIEW = "review"
    DEBUG = "debug"
    TEST = "test"
    DOCUMENT = "document"
    MIGRATE = "migrate"
    DESIGN = "design"
    OPTIMIZE = "optimize"


@dataclass(frozen=True)
class CodeSignal:
    kind: CodeSignalKind
    severity: int
    message: str
    evidence: str = ""
    remediation: str = ""


@dataclass(frozen=True)
class CodeTask:
    kind: CodeTaskKind
    priority: int
    rationale: str
    target: str = ""


@dataclass(frozen=True)
class CodeIntelligenceReport:
    signals: tuple[CodeSignal, ...]
    tasks: tuple[CodeTask, ...]
    complexity_score: float
    testability_score: float
    documentation_score: float


@dataclass
class CodeIntelligenceEngine:
    """Small static-policy engine for Jeeves coding lessons.

    The engine is intentionally conservative: signals are teaching prompts,
    not claims that a defect definitely exists.
    """

    max_signals: int = 20

    def analyze(self, code: str, language: str = "python") -> CodeIntelligenceReport:
        signals = list(self._bug_signals(code, language))
        signals.extend(self._security_signals(code, language))
        signals.extend(self._complexity_signals(code, language))
        signals.extend(self._test_signals(code, language))
        signals.extend(self._documentation_signals(code, language))
        signals.sort(key=lambda item: (-item.severity, item.kind.value, item.message))
        signals = signals[: self.max_signals]

        complexity = self._complexity_score(code)
        tests = self._testability_score(code)
        docs = self._documentation_score(code, language)
        tasks = self._tasks(signals, complexity, tests, docs)
        return CodeIntelligenceReport(tuple(signals), tuple(tasks), complexity, tests, docs)

    def prioritize_learning(self, report: CodeIntelligenceReport) -> tuple[CodeTask, ...]:
        """Return a learner-facing order: correctness before polish."""
        return tuple(sorted(report.tasks, key=lambda task: (-task.priority, task.kind.value)))

    def _bug_signals(self, code: str, language: str) -> Iterable[CodeSignal]:
        if re.search(r"except\s*:\s*(?:\n|$)", code):
            yield CodeSignal(CodeSignalKind.BUG_RISK, 8, "Bare exception handling can hide unrelated failures.", "except:", "Catch the narrowest expected exception and preserve diagnostics.")
        if re.search(r"except\s+Exception\s*:\s*(?:\n|$)", code):
            yield CodeSignal(CodeSignalKind.BUG_RISK, 6, "Broad exception handling may conceal programming errors.", "except Exception:", "Handle known failure modes explicitly.")
        if re.search(r"\b(?:eval|exec)\s*\(", code):
            yield CodeSignal(CodeSignalKind.SECURITY, 10, "Dynamic code execution is a high-risk boundary.", "eval/exec", "Avoid it or constrain inputs through a safe parser/sandbox.")
        if language.lower() in {"python", "py"} and re.search(r"\bassert\s+[^\n]+", code):
            yield CodeSignal(CodeSignalKind.BUG_RISK, 3, "Assertions may be disabled in optimized Python runs.", "assert", "Use explicit validation for runtime invariants.")

    def _security_signals(self, code: str, language: str) -> Iterable[CodeSignal]:
        patterns = [
            (r"subprocess\.(?:run|Popen|call)\([^\n]*shell\s*=\s*True", "Shell execution deserves explicit input validation.", 9),
            (r"(?:password|secret|api[_-]?key)\s*=\s*['\"]", "A credential-like literal appears in source.", 10),
            (r"(?:SELECT|INSERT|UPDATE|DELETE)[^\n]*\+", "String concatenation near SQL may permit injection.", 9),
        ]
        for pattern, message, severity in patterns:
            if re.search(pattern, code, re.IGNORECASE):
                yield CodeSignal(CodeSignalKind.SECURITY, severity, message, re.search(pattern, code, re.IGNORECASE).group(0), "Use parameterization, secret injection, and constrained process APIs.")

    def _complexity_signals(self, code: str, language: str) -> Iterable[CodeSignal]:
        nested = re.findall(r"\n\s+for\s+[^\n]+:\s*\n\s+for\s+", code)
        if nested:
            yield CodeSignal(CodeSignalKind.COMPLEXITY, 5, "Nested iteration may be quadratic or worse.", "nested loops", "Measure the data size and consider indexing, sets, maps, or a different algorithm.")
        functions = len(re.findall(r"\b(?:def|function)\s+\w+", code))
        branches = len(re.findall(r"\b(?:if|elif|else|for|while|match|case)\b", code))
        if functions and branches / functions > 8:
            yield CodeSignal(CodeSignalKind.COMPLEXITY, 5, "Functions contain a high branch density.", f"{branches} control-flow keywords / {functions} functions", "Split responsibilities and test decision boundaries separately.")

    def _test_signals(self, code: str, language: str) -> Iterable[CodeSignal]:
        has_tests = bool(re.search(r"\b(?:pytest|unittest|describe|it\(|test_|@Test)\b", code))
        functions = len(re.findall(r"\b(?:def|function)\s+\w+", code))
        if functions >= 2 and not has_tests:
            yield CodeSignal(CodeSignalKind.TEST_GAP, 7, "Multiple executable units are present without visible tests.", f"{functions} functions", "Design unit tests for happy paths, boundaries, and failure modes.")

    def _documentation_signals(self, code: str, language: str) -> Iterable[CodeSignal]:
        functions = len(re.findall(r"\b(?:def|function|class)\s+\w+", code))
        docs = len(re.findall(r"\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''", code))
        if functions >= 3 and docs == 0:
            yield CodeSignal(CodeSignalKind.DOCUMENTATION, 3, "Public behavior may be difficult to discover without documentation.", f"{functions} declarations", "Document purpose, inputs, outputs, invariants, and examples.")

    def _complexity_score(self, code: str) -> float:
        lines = max(1, len(code.splitlines()))
        branches = len(re.findall(r"\b(?:if|elif|else|for|while|match|case)\b", code))
        nesting = len(re.findall(r"\n\s{8,}(?:if|for|while|with|try)\b", code))
        return max(0.0, min(1.0, 1.0 - (branches / lines) * 1.5 - nesting / max(lines, 1)))

    def _testability_score(self, code: str) -> float:
        functions = len(re.findall(r"\b(?:def|function)\s+\w+", code))
        tests = len(re.findall(r"\b(?:test_|pytest|unittest|describe|it\()", code))
        if not functions:
            return 1.0
        return min(1.0, tests / max(1, functions / 2))

    def _documentation_score(self, code: str, language: str) -> float:
        declarations = len(re.findall(r"\b(?:def|function|class)\s+\w+", code))
        docs = len(re.findall(r"\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''", code))
        if not declarations:
            return 1.0
        return min(1.0, docs / declarations)

    def _tasks(self, signals: Sequence[CodeSignal], complexity: float, tests: float, docs: float) -> list[CodeTask]:
        tasks: list[CodeTask] = []
        if any(s.kind == CodeSignalKind.SECURITY for s in signals):
            tasks.append(CodeTask(CodeTaskKind.REVIEW, 10, "Resolve security-sensitive findings before feature work."))
        if any(s.kind == CodeSignalKind.BUG_RISK for s in signals):
            tasks.append(CodeTask(CodeTaskKind.DEBUG, 9, "Investigate correctness risks and reproduce the suspected failure."))
        if tests < 0.6:
            tasks.append(CodeTask(CodeTaskKind.TEST, 8, "Add tests that expose boundaries and regressions."))
        if complexity < 0.55:
            tasks.append(CodeTask(CodeTaskKind.OPTIMIZE, 5, "Measure complexity before changing implementation."))
        if docs < 0.6:
            tasks.append(CodeTask(CodeTaskKind.DOCUMENT, 3, "Document behavior so another learner can reason about the code."))
        if not tasks:
            tasks.append(CodeTask(CodeTaskKind.REVIEW, 4, "Review the implementation and explain its trade-offs."))
        return tasks
