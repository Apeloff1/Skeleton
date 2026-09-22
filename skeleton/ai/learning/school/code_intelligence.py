"""Deterministic code-intelligence policies mined from Tutolage."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
from typing import Iterable, Sequence

class CodeSignalKind(str, Enum):
    BUG_RISK = "bug_risk"
    SECURITY = "security"
    COMPLEXITY = "complexity"
    TEST_GAP = "test_gap"
    DOCUMENTATION = "documentation"

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
    max_signals: int = 20

    def analyze(self, code: str, language: str = "python") -> CodeIntelligenceReport:
        signals = [*self._bug_signals(code, language), *self._security_signals(code), *self._complexity_signals(code), *self._test_signals(code), *self._documentation_signals(code)]
        signals.sort(key=lambda x: (-x.severity, x.kind.value, x.message))
        signals = signals[: self.max_signals]
        complexity = self._complexity_score(code)
        tests = self._testability_score(code)
        docs = self._documentation_score(code)
        return CodeIntelligenceReport(tuple(signals), tuple(self._tasks(signals, complexity, tests, docs)), complexity, tests, docs)

    def prioritize_learning(self, report: CodeIntelligenceReport) -> tuple[CodeTask, ...]:
        return tuple(sorted(report.tasks, key=lambda x: (-x.priority, x.kind.value)))

    def _bug_signals(self, code: str, language: str) -> list[CodeSignal]:
        out = []
        if re.search(r"except\s*:\s*(?:\n|$)", code):
            out.append(CodeSignal(CodeSignalKind.BUG_RISK, 8, "Bare exception handling can hide unrelated failures.", "except:", "Catch the narrowest expected exception."))
        if re.search(r"except\s+Exception\s*:\s*(?:\n|$)", code):
            out.append(CodeSignal(CodeSignalKind.BUG_RISK, 6, "Broad exception handling may conceal programming errors.", "except Exception:", "Handle known failure modes explicitly."))
        if language.lower() in {"python", "py"} and re.search(r"\bassert\s+[^\n]+", code):
            out.append(CodeSignal(CodeSignalKind.BUG_RISK, 3, "Assertions may be disabled in optimized Python runs.", "assert", "Use explicit runtime validation for external inputs."))
        return out

    def _security_signals(self, code: str) -> list[CodeSignal]:
        out = []
        for pattern, message, severity in [(r"\b(?:eval|exec)\s*\(", "Dynamic code execution is a high-risk boundary.", 10), (r"subprocess\.(?:run|Popen|call)\([^\n]*shell\s*=\s*True", "Shell execution deserves explicit input validation.", 9), (r"(?:password|secret|api[_-]?key)\s*=\s*['\"]", "A credential-like literal appears in source.", 10), (r"(?:SELECT|INSERT|UPDATE|DELETE)[^\n]*\+", "String concatenation near SQL may permit injection.", 9)]:
            match = re.search(pattern, code, re.IGNORECASE)
            if match:
                out.append(CodeSignal(CodeSignalKind.SECURITY, severity, message, match.group(0), "Use parameterization, secret injection, and constrained process APIs."))
        return out

    def _complexity_signals(self, code: str) -> list[CodeSignal]:
        out = []
        if re.search(r"\n\s+for\s+[^\n]+:\s*\n\s+for\s+", code):
            out.append(CodeSignal(CodeSignalKind.COMPLEXITY, 5, "Nested iteration may be quadratic or worse.", "nested loops", "Measure data size and consider indexing or a different algorithm."))
        functions = len(re.findall(r"\b(?:def|function)\s+\w+", code))
        branches = len(re.findall(r"\b(?:if|elif|else|for|while|match|case)\b", code))
        if functions and branches / functions > 8:
            out.append(CodeSignal(CodeSignalKind.COMPLEXITY, 5, "Functions contain high branch density.", f"{branches} control-flow keywords / {functions} functions", "Split responsibilities and test decision boundaries separately."))
        return out

    def _test_signals(self, code: str) -> list[CodeSignal]:
        functions = len(re.findall(r"\b(?:def|function)\s+\w+", code))
        if functions >= 2 and not re.search(r"\b(?:pytest|unittest|describe|it\(|test_|@Test)\b", code):
            return [CodeSignal(CodeSignalKind.TEST_GAP, 7, "Multiple executable units are present without visible tests.", f"{functions} functions", "Design tests for happy paths, boundaries, and failures.")]
        return []

    def _documentation_signals(self, code: str) -> list[CodeSignal]:
        declarations = len(re.findall(r"\b(?:def|function|class)\s+\w+", code))
        docs = len(re.findall(r"\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''", code))
        if declarations >= 3 and docs == 0:
            return [CodeSignal(CodeSignalKind.DOCUMENTATION, 3, "Public behavior may be difficult to discover without documentation.", f"{declarations} declarations", "Document purpose, inputs, outputs, invariants, and examples.")]
        return []

    def _complexity_score(self, code: str) -> float:
        lines = max(1, len(code.splitlines()))
        branches = len(re.findall(r"\b(?:if|elif|else|for|while|match|case)\b", code))
        nesting = len(re.findall(r"\n\s{8,}(?:if|for|while|with|try)\b", code))
        return max(0.0, min(1.0, 1.0 - (branches / lines) * 1.5 - nesting / lines))

    def _testability_score(self, code: str) -> float:
        functions = len(re.findall(r"\b(?:def|function)\s+\w+", code))
        tests = len(re.findall(r"\b(?:test_|pytest|unittest|describe|it\()", code))
        return 1.0 if not functions else min(1.0, tests / max(1, functions / 2))

    def _documentation_score(self, code: str) -> float:
        declarations = len(re.findall(r"\b(?:def|function|class)\s+\w+", code))
        docs = len(re.findall(r"\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''", code))
        return 1.0 if not declarations else min(1.0, docs / declarations)

    def _tasks(self, signals: Sequence[CodeSignal], complexity: float, tests: float, docs: float) -> list[CodeTask]:
        tasks = []
        if any(x.kind == CodeSignalKind.SECURITY for x in signals): tasks.append(CodeTask(CodeTaskKind.REVIEW, 10, "Resolve security-sensitive findings before feature work."))
        if any(x.kind == CodeSignalKind.BUG_RISK for x in signals): tasks.append(CodeTask(CodeTaskKind.DEBUG, 9, "Investigate correctness risks and reproduce the suspected failure."))
        if tests < 0.6: tasks.append(CodeTask(CodeTaskKind.TEST, 8, "Add tests that expose boundaries and regressions."))
        if complexity < 0.55: tasks.append(CodeTask(CodeTaskKind.OPTIMIZE, 5, "Measure complexity before changing implementation."))
        if docs < 0.6: tasks.append(CodeTask(CodeTaskKind.DOCUMENT, 3, "Document behavior so another learner can reason about the code."))
        return tasks or [CodeTask(CodeTaskKind.REVIEW, 4, "Review the implementation and explain its trade-offs.")]
