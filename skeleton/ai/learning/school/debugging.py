"""Deterministic debugging policy mined from Tutolage's AI debugger."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Sequence
from skeleton.school.code_intelligence import CodeIntelligenceReport, CodeSignalKind

class DebugFocus(str, Enum):
    ROOT_CAUSE="root_cause"; SECURITY="security"; PERFORMANCE="performance"; CORRECTNESS="correctness"; TESTING="testing"
class DebugAction(str, Enum):
    REPRODUCE="reproduce"; INSPECT="inspect"; ISOLATE="isolate"; TEST="test"; MEASURE="measure"; REVIEW="review"; EXPLAIN="explain"

_ACTION_PRIORITY = {
    DebugAction.ISOLATE: 0, DebugAction.REPRODUCE: 1, DebugAction.INSPECT: 2,
    DebugAction.TEST: 3, DebugAction.MEASURE: 4, DebugAction.REVIEW: 5, DebugAction.EXPLAIN: 6,
}

@dataclass(frozen=True)
class DebugHypothesis:
    focus: DebugFocus; statement: str; evidence: str; confidence: float
@dataclass(frozen=True)
class DebugExperiment:
    action: DebugAction; prompt: str; expected_evidence: str; learner_owned: bool = True
@dataclass(frozen=True)
class DebugPlan:
    hypotheses: tuple[DebugHypothesis, ...]; experiments: tuple[DebugExperiment, ...]; next_step: DebugAction; rationale: tuple[str, ...]

class DebuggingPolicy:
    """Convert code-intelligence findings into teachable debugging steps."""
    def plan(self, report: CodeIntelligenceReport, *, error_context: str = "") -> DebugPlan:
        hypotheses: list[DebugHypothesis] = []; experiments: list[DebugExperiment] = []; rationale: list[str] = []
        kinds = {signal.kind for signal in report.signals}
        if CodeSignalKind.SECURITY in kinds:
            for signal in report.signals:
                if signal.kind == CodeSignalKind.SECURITY:
                    hypotheses.append(DebugHypothesis(DebugFocus.SECURITY, signal.message, signal.evidence, min(1.0, 0.55 + signal.severity / 20)))
            experiments.append(DebugExperiment(DebugAction.ISOLATE, "Identify the smallest input or code path that reaches the security-sensitive boundary.", "A minimal reproducer or constrained input path."))
            rationale.append("Security findings are investigated before feature work.")
        if CodeSignalKind.BUG_RISK in kinds:
            for signal in report.signals:
                if signal.kind == CodeSignalKind.BUG_RISK:
                    hypotheses.append(DebugHypothesis(DebugFocus.CORRECTNESS, signal.message, signal.evidence, min(1.0, 0.5 + signal.severity / 20)))
            experiments.append(DebugExperiment(DebugAction.REPRODUCE, "Create the smallest failing example and state what you expected versus what occurred.", "A reproducible failure with an explicit expected/actual difference."))
            rationale.append("Correctness risks become reproducible evidence rather than immediate auto-fixes.")
        if error_context:
            experiments.append(DebugExperiment(DebugAction.INSPECT, "Trace the supplied error from its first meaningful frame to the code that produced the bad state.", "The earliest actionable frame and the state that caused it."))
            rationale.append("Error context is used to locate a causal boundary.")
        if CodeSignalKind.COMPLEXITY in kinds:
            hypotheses.append(DebugHypothesis(DebugFocus.PERFORMANCE, "A complexity or bottleneck signal may be contributing to slow execution.", "Complexity signals from static inspection.", 0.65))
            experiments.append(DebugExperiment(DebugAction.MEASURE, "Measure the suspected path before changing the algorithm or data structure.", "A timing, count, or profile comparison that distinguishes the hypothesis."))
            rationale.append("Performance changes should be justified by measurement.")
        if CodeSignalKind.TEST_GAP in kinds:
            experiments.append(DebugExperiment(DebugAction.TEST, "Write a focused regression test for the suspected boundary or failure mode.", "A test that fails before the fix and passes after it."))
            rationale.append("A regression test turns debugging into durable learning evidence.")
        if not hypotheses and not experiments:
            experiments.append(DebugExperiment(DebugAction.REVIEW, "Explain the code path, identify one assumption, and propose a test of that assumption.", "An explicit assumption plus evidence supporting or rejecting it."))
            rationale.append("No strong static signal exists; use hypothesis-driven review instead of guessing.")
        ordered = sorted(experiments, key=lambda item: (_ACTION_PRIORITY[item.action], item.prompt))
        return DebugPlan(tuple(hypotheses), tuple(ordered), ordered[0].action, tuple(rationale))

    def learning_signal(self, plan: DebugPlan, *, successful: bool, explanation_quality: float = 0.0) -> str:
        if successful and explanation_quality >= 0.7: return "independent_debugging_evidence"
        if successful: return "guided_debugging_evidence"
        return "debugging_misconception_or_gap"
