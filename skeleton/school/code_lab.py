"""Provider-agnostic coding-school feedback loop.

Mined from Tutolage's AI debugger and advanced code-intelligence surfaces:
explain/debug, test generation, bug prediction, code review, security and
performance analysis.  The core does not call an LLM; it creates structured
signals and a rubric that Jeeves can hand to any model or tool adapter.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
from typing import List


class FindingSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class CodeFinding:
    category: str
    severity: FindingSeverity
    message: str
    line: int | None = None
    remediation: str | None = None


@dataclass(frozen=True)
class CodeTask:
    task_id: str
    skill_id: str
    prompt: str
    language: str = "python"
    expected_concepts: tuple[str, ...] = ()
    difficulty: int = 1
    time_limit_minutes: int = 30


@dataclass
class CodeReview:
    task_id: str
    score: float
    findings: List[CodeFinding] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    next_step: str = ""
    tests_suggested: List[str] = field(default_factory=list)


class CodeLabEngine:
    """Deterministic first-pass reviewer for a model-assisted coding tutor."""

    def review(self, task: CodeTask, code: str) -> CodeReview:
        findings: List[CodeFinding] = []
        strengths: List[str] = []
        tests: List[str] = []
        score = 1.0

        if not code.strip():
            return CodeReview(task.task_id, 0.0, [CodeFinding("submission", FindingSeverity.HIGH, "No code submitted.")], next_step="start_with_a_minimal_solution")

        tree = None
        if task.language.lower() == "python":
            try:
                tree = ast.parse(code)
                strengths.append("Python syntax parses successfully.")
            except SyntaxError as exc:
                findings.append(
                    CodeFinding(
                        "syntax",
                        FindingSeverity.CRITICAL,
                        exc.msg,
                        exc.lineno,
                        "Fix the syntax error, then rerun the review.",
                    )
                )
                return CodeReview(task.task_id, 0.2, findings, next_step="repair_syntax")

        if len(code.splitlines()) > 160:
            findings.append(CodeFinding("maintainability", FindingSeverity.MEDIUM, "Solution is unusually large for a single task; consider decomposition.", remediation="Extract cohesive helpers or classes."))
            score -= 0.08
        if "TODO" in code or "pass" in code:
            findings.append(CodeFinding("completeness", FindingSeverity.MEDIUM, "Submission contains an unfinished marker.", remediation="Replace placeholders with tested behavior."))
            score -= 0.15
        if "except:" in code:
            findings.append(CodeFinding("error_handling", FindingSeverity.MEDIUM, "Bare exception handling can hide real failures.", remediation="Catch the narrow exception types you expect."))
            score -= 0.1
        if "eval(" in code or "exec(" in code:
            findings.append(CodeFinding("security", FindingSeverity.HIGH, "Dynamic code execution detected.", remediation="Avoid eval/exec; use explicit parsing or a constrained interpreter."))
            score -= 0.2
        if task.expected_concepts:
            missing = [concept for concept in task.expected_concepts if concept.lower() not in code.lower()]
            if missing:
                findings.append(CodeFinding("learning_objective", FindingSeverity.MEDIUM, f"Expected concepts are not evident: {', '.join(missing)}", remediation="Explain or implement the missing concepts explicitly."))
                score -= min(0.25, 0.06 * len(missing))
            else:
                strengths.append("Expected task concepts are represented in the submission.")

        if tree is not None:
            function_count = sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in ast.walk(tree))
            if function_count:
                strengths.append(f"Uses {function_count} named function(s), making the solution easier to test.")
            if any(isinstance(node, ast.Assert) for node in ast.walk(tree)):
                strengths.append("Includes at least one assertion for executable self-checking.")
            else:
                tests.append("Add a happy-path assertion for the primary learning objective.")

        if not findings:
            strengths.append("No deterministic red flags found in the first-pass review.")
        score = max(0.0, min(1.0, score))
        if score < 0.5:
            next_step = "repair_highest_severity_finding"
        elif score < 0.75:
            next_step = "guided_revision_then_retest"
        elif score < 0.9:
            next_step = "independent_test_and_explain"
        else:
            next_step = "transfer_challenge"
        return CodeReview(task.task_id, score, findings, strengths, next_step, tests)
