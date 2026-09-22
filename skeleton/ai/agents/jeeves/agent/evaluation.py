"""Offline evaluation, calibration, and invariant checks for Jeeves.

A serious agent needs falsifiable quality gates.  This module evaluates runs
without asking the model whether it did well: success criteria are encoded as
host-side expectations over results, traces, claims, evidence, tools, budgets,
and deterministic replay fingerprints.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from .telemetry import TraceLedger
from .types import (
    AgentContractError,
    AgentResult,
    Claim,
    TerminationReason,
    finite_number,
    json_safe,
    probability,
    require_id,
    stable_fingerprint,
)


@dataclass(frozen=True, slots=True)
class EvalExpectation:
    must_succeed: bool | None = True
    allowed_termination: tuple[TerminationReason, ...] = (TerminationReason.GOAL_REACHED,)
    required_answer_substrings: tuple[str, ...] = ()
    forbidden_answer_substrings: tuple[str, ...] = ()
    minimum_grounded_claims: int = 0
    maximum_tool_calls: int | None = None
    maximum_model_calls: int | None = None
    maximum_total_tokens: int | None = None
    require_trace_fingerprint: bool = True

    def __post_init__(self) -> None:
        if self.must_succeed is not None and not isinstance(self.must_succeed, bool):
            raise AgentContractError("must_succeed must be bool or None")
        allowed = tuple(
            item if isinstance(item, TerminationReason) else TerminationReason(str(item))
            for item in self.allowed_termination
        )
        object.__setattr__(self, "allowed_termination", allowed)
        object.__setattr__(
            self,
            "required_answer_substrings",
            tuple(str(item).strip() for item in self.required_answer_substrings if str(item).strip()),
        )
        object.__setattr__(
            self,
            "forbidden_answer_substrings",
            tuple(str(item).strip() for item in self.forbidden_answer_substrings if str(item).strip()),
        )
        if isinstance(self.minimum_grounded_claims, bool) or not isinstance(self.minimum_grounded_claims, int) or self.minimum_grounded_claims < 0:
            raise AgentContractError("minimum_grounded_claims must be a non-negative integer")
        for name in ("maximum_tool_calls", "maximum_model_calls", "maximum_total_tokens"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise AgentContractError(f"{name} must be a non-negative integer or None")


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    description: str
    expectation: EvalExpectation
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", require_id("case_id", self.case_id))
        if not isinstance(self.description, str) or not self.description.strip():
            raise AgentContractError("evaluation description must be non-empty")
        object.__setattr__(self, "description", self.description.strip()[:4096])
        if not isinstance(self.expectation, EvalExpectation):
            raise AgentContractError("expectation must be EvalExpectation")
        object.__setattr__(self, "tags", tuple(sorted(set(str(tag).strip().lower() for tag in self.tags if str(tag).strip()))))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    weight: float
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise AgentContractError("check name must be non-empty")
        if not isinstance(self.passed, bool):
            raise AgentContractError("passed must be boolean")
        weight = finite_number("weight", self.weight)
        if weight < 0:
            raise AgentContractError("check weight must be non-negative")
        object.__setattr__(self, "weight", weight)
        object.__setattr__(self, "message", str(self.message).strip()[:4096])
        object.__setattr__(self, "details", json_safe(dict(self.details)))


@dataclass(frozen=True, slots=True)
class EvalResult:
    case_id: str
    run_id: str
    score: float
    passed: bool
    checks: tuple[CheckResult, ...]
    result_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", require_id("case_id", self.case_id))
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        object.__setattr__(self, "score", probability("score", self.score))
        if any(not isinstance(check, CheckResult) for check in self.checks):
            raise AgentContractError("checks must contain CheckResult values")


class RunEvaluator:
    def evaluate(self, case: EvalCase, result: AgentResult) -> EvalResult:
        if not isinstance(case, EvalCase):
            raise TypeError("case must be EvalCase")
        if not isinstance(result, AgentResult):
            raise TypeError("result must be AgentResult")
        expectation = case.expectation
        checks: list[CheckResult] = []

        if expectation.must_succeed is not None:
            checks.append(
                CheckResult(
                    name="success",
                    passed=result.success is expectation.must_succeed,
                    weight=2.0,
                    message=f"expected success={expectation.must_succeed}, got {result.success}",
                )
            )
        checks.append(
            CheckResult(
                name="termination",
                passed=result.reason in expectation.allowed_termination,
                weight=2.0,
                message=f"termination={result.reason.value}",
                details={"allowed": [item.value for item in expectation.allowed_termination]},
            )
        )
        answer_lower = result.answer.lower()
        for required in expectation.required_answer_substrings:
            checks.append(
                CheckResult(
                    name=f"answer-required:{required[:40]}",
                    passed=required.lower() in answer_lower,
                    weight=1.0,
                    message=f"required substring present: {required}",
                )
            )
        for forbidden in expectation.forbidden_answer_substrings:
            checks.append(
                CheckResult(
                    name=f"answer-forbidden:{forbidden[:40]}",
                    passed=forbidden.lower() not in answer_lower,
                    weight=1.5,
                    message=f"forbidden substring absent: {forbidden}",
                )
            )
        checks.append(
            CheckResult(
                name="grounded-claims",
                passed=len(result.claims) >= expectation.minimum_grounded_claims,
                weight=1.5,
                message=f"grounded claims={len(result.claims)}",
                details={"minimum": expectation.minimum_grounded_claims},
            )
        )
        if expectation.maximum_tool_calls is not None:
            checks.append(
                CheckResult(
                    name="tool-budget",
                    passed=result.usage.tool_calls <= expectation.maximum_tool_calls,
                    weight=1.0,
                    message=f"tool calls={result.usage.tool_calls}",
                    details={"maximum": expectation.maximum_tool_calls},
                )
            )
        if expectation.maximum_model_calls is not None:
            checks.append(
                CheckResult(
                    name="model-budget",
                    passed=result.usage.model_calls <= expectation.maximum_model_calls,
                    weight=1.0,
                    message=f"model calls={result.usage.model_calls}",
                    details={"maximum": expectation.maximum_model_calls},
                )
            )
        if expectation.maximum_total_tokens is not None:
            checks.append(
                CheckResult(
                    name="token-budget",
                    passed=result.usage.total_tokens <= expectation.maximum_total_tokens,
                    weight=1.0,
                    message=f"tokens={result.usage.total_tokens}",
                    details={"maximum": expectation.maximum_total_tokens},
                )
            )
        if expectation.require_trace_fingerprint:
            checks.append(
                CheckResult(
                    name="trace-fingerprint",
                    passed=bool(result.trace_fingerprint),
                    weight=1.0,
                    message="run has an audit trace fingerprint",
                )
            )
        total_weight = sum(check.weight for check in checks)
        passed_weight = sum(check.weight for check in checks if check.passed)
        score = passed_weight / total_weight if total_weight else 1.0
        passed = all(check.passed for check in checks)
        result_fingerprint = stable_fingerprint(
            {
                "case": case.case_id,
                "run": result.run_id,
                "score": score,
                "checks": [(check.name, check.passed, check.weight) for check in checks],
                "answer": stable_fingerprint(result.answer),
                "trace": result.trace_fingerprint,
            }
        )
        return EvalResult(
            case_id=case.case_id,
            run_id=result.run_id,
            score=score,
            passed=passed,
            checks=tuple(checks),
            result_fingerprint=result_fingerprint,
        )


@dataclass(frozen=True, slots=True)
class CalibrationSample:
    confidence: float
    correct: bool
    channel: str = "default"

    def __post_init__(self) -> None:
        object.__setattr__(self, "confidence", probability("confidence", self.confidence))
        if not isinstance(self.correct, bool):
            raise AgentContractError("correct must be boolean")
        if not isinstance(self.channel, str) or not self.channel.strip():
            raise AgentContractError("calibration channel must be non-empty")
        object.__setattr__(self, "channel", self.channel.strip()[:128])


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    count: int
    accuracy: float
    mean_confidence: float
    brier_score: float
    expected_calibration_error: float
    maximum_calibration_error: float
    bins: tuple[Mapping[str, Any], ...]


class CalibrationEvaluator:
    def __init__(self, *, bins: int = 10) -> None:
        if isinstance(bins, bool) or not isinstance(bins, int) or bins < 2 or bins > 100:
            raise ValueError("bins must be an integer in [2, 100]")
        self.bins = bins

    def evaluate(self, samples: Sequence[CalibrationSample]) -> CalibrationReport:
        if not samples:
            return CalibrationReport(0, 0.0, 0.0, 0.0, 0.0, 0.0, ())
        if any(not isinstance(sample, CalibrationSample) for sample in samples):
            raise TypeError("samples must contain CalibrationSample values")
        accuracy = sum(1 for sample in samples if sample.correct) / len(samples)
        mean_confidence = statistics.fmean(sample.confidence for sample in samples)
        brier = statistics.fmean((sample.confidence - (1.0 if sample.correct else 0.0)) ** 2 for sample in samples)

        bins: list[dict[str, Any]] = []
        ece = 0.0
        mce = 0.0
        for index in range(self.bins):
            lower = index / self.bins
            upper = (index + 1) / self.bins
            if index == self.bins - 1:
                members = [sample for sample in samples if lower <= sample.confidence <= upper]
            else:
                members = [sample for sample in samples if lower <= sample.confidence < upper]
            if not members:
                continue
            bin_conf = statistics.fmean(sample.confidence for sample in members)
            bin_acc = sum(1 for sample in members if sample.correct) / len(members)
            gap = abs(bin_conf - bin_acc)
            weight = len(members) / len(samples)
            ece += weight * gap
            mce = max(mce, gap)
            bins.append(
                {
                    "lower": lower,
                    "upper": upper,
                    "count": len(members),
                    "mean_confidence": bin_conf,
                    "accuracy": bin_acc,
                    "gap": gap,
                }
            )
        return CalibrationReport(
            count=len(samples),
            accuracy=accuracy,
            mean_confidence=mean_confidence,
            brier_score=brier,
            expected_calibration_error=ece,
            maximum_calibration_error=mce,
            bins=tuple(bins),
        )


@dataclass(frozen=True, slots=True)
class InvariantViolation:
    invariant: str
    message: str
    severity: str = "error"
    details: Mapping[str, Any] = field(default_factory=dict)


class AgentInvariantChecker:
    """Check non-negotiable runtime properties on completed results."""

    def check(self, result: AgentResult) -> tuple[InvariantViolation, ...]:
        if not isinstance(result, AgentResult):
            raise TypeError("result must be AgentResult")
        violations: list[InvariantViolation] = []
        if result.success and result.reason is not TerminationReason.GOAL_REACHED:
            violations.append(
                InvariantViolation(
                    "success-implies-goal-reached",
                    "successful result has non-success termination reason",
                    details={"reason": result.reason.value},
                )
            )
        if result.usage.tool_calls < len(result.observations):
            violations.append(
                InvariantViolation(
                    "tool-usage-covers-observations",
                    "observation count exceeds recorded tool calls",
                    details={"tool_calls": result.usage.tool_calls, "observations": len(result.observations)},
                )
            )
        if result.plan is not None and result.plan.goal_id != result.goal_id:
            violations.append(
                InvariantViolation(
                    "plan-goal-binding",
                    "result plan belongs to a different goal",
                    details={"plan_goal": result.plan.goal_id, "result_goal": result.goal_id},
                )
            )
        evidence_by_id: dict[str, str] = {}
        for claim in result.claims:
            if claim.derived and not claim.evidence:
                violations.append(
                    InvariantViolation(
                        "derived-claims-are-grounded",
                        f"derived claim {claim.claim_id} has no evidence",
                    )
                )
            for ref in claim.evidence:
                prior = evidence_by_id.get(ref.evidence_id)
                if prior is not None and prior != ref.fingerprint:
                    violations.append(
                        InvariantViolation(
                            "evidence-id-is-content-addressed",
                            f"evidence id {ref.evidence_id} appears with conflicting fingerprints",
                        )
                    )
                evidence_by_id[ref.evidence_id] = ref.fingerprint
        if not result.trace_fingerprint:
            violations.append(InvariantViolation("trace-exists", "result has no trace fingerprint"))
        return tuple(violations)


@dataclass(frozen=True, slots=True)
class SuiteReport:
    total: int
    passed: int
    mean_score: float
    minimum_score: float
    results: tuple[EvalResult, ...]
    fingerprint: str


class EvaluationSuite:
    def __init__(self, evaluator: RunEvaluator | None = None) -> None:
        self.evaluator = evaluator or RunEvaluator()

    def evaluate(self, pairs: Iterable[tuple[EvalCase, AgentResult]]) -> SuiteReport:
        results = tuple(self.evaluator.evaluate(case, result) for case, result in pairs)
        if not results:
            return SuiteReport(0, 0, 0.0, 0.0, (), stable_fingerprint([]))
        passed = sum(1 for result in results if result.passed)
        scores = [result.score for result in results]
        fingerprint = stable_fingerprint(
            [(result.case_id, result.result_fingerprint, result.score, result.passed) for result in results]
        )
        return SuiteReport(
            total=len(results),
            passed=passed,
            mean_score=statistics.fmean(scores),
            minimum_score=min(scores),
            results=results,
            fingerprint=fingerprint,
        )


def claim_calibration_samples(
    claims: Sequence[Claim],
    correctness: Mapping[str, bool],
    *,
    channel: str = "claims",
) -> tuple[CalibrationSample, ...]:
    samples: list[CalibrationSample] = []
    for claim in claims:
        if claim.claim_id not in correctness:
            continue
        samples.append(CalibrationSample(claim.confidence, bool(correctness[claim.claim_id]), channel))
    return tuple(samples)
