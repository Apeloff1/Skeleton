"""Offline developmental evaluation for local training feedback.

This evaluator is deliberately separate from promotion holdouts and independent
promotion policy. It compares an exact baseline artifact with an exact candidate
artifact on a bounded, deterministic development suite, emits content-addressed
case evidence, and can translate the measured gain into the existing adaptive
training allocator.

It has no network, tool, side-effect, promotion, or production authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import threading
from typing import Mapping, Sequence

from .artifact import LocalModelArtifactError, load_local_model_artifact
from .local import LocalInferenceRequest
from .training_allocation import MethodValidationObservation
from .training_methods import TrainingMethod


_MAX_CASES = 512
_MAX_TERM_COUNT = 128
_WS = re.compile(r"\s+")


class DevelopmentalEvaluationError(RuntimeError):
    """Developmental evaluation evidence is invalid or cannot be executed."""


def _json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DevelopmentalEvaluationError(
            "developmental evaluation is not deterministic JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise DevelopmentalEvaluationError(f"{field} must be sha256 text")
    result = value.strip().lower()
    if (
        len(result) != 64
        or any(ch not in "0123456789abcdef" for ch in result)
    ):
        raise DevelopmentalEvaluationError(
            f"{field} must be lowercase sha256"
        )
    return result


def _text(value: object, field: str, *, maximum: int = 16_384) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DevelopmentalEvaluationError(
            f"{field} must be non-empty text"
        )
    result = value.strip()
    if len(result) > maximum:
        raise DevelopmentalEvaluationError(
            f"{field} exceeds maximum length"
        )
    return result


def _normalized_term(value: object, field: str) -> str:
    return _WS.sub(" ", _text(value, field, maximum=512).casefold())


def _finite_weight(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DevelopmentalEvaluationError("case weight must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 < result <= 1_000_000.0:
        raise DevelopmentalEvaluationError(
            "case weight must be finite and positive"
        )
    return result


@dataclass(frozen=True, slots=True)
class DevelopmentalEvalCase:
    """One deterministic local development case."""

    case_id: str
    prompt: str
    required_terms: tuple[str, ...]
    forbidden_terms: tuple[str, ...] = ()
    weight: float = 1.0
    max_output_tokens: int = 32
    seed: int = 0

    def __post_init__(self) -> None:
        case_id = _text(self.case_id, "case_id", maximum=256)
        prompt = _text(self.prompt, "prompt")
        required = tuple(
            dict.fromkeys(
                _normalized_term(item, "required_term")
                for item in self.required_terms
            )
        )
        forbidden = tuple(
            dict.fromkeys(
                _normalized_term(item, "forbidden_term")
                for item in self.forbidden_terms
            )
        )
        if not required:
            raise DevelopmentalEvaluationError(
                "development case requires at least one required term"
            )
        if (
            len(required) > _MAX_TERM_COUNT
            or len(forbidden) > _MAX_TERM_COUNT
        ):
            raise DevelopmentalEvaluationError(
                "development case term inventory exceeds hard bound"
            )
        if set(required) & set(forbidden):
            raise DevelopmentalEvaluationError(
                "required and forbidden terms must be disjoint"
            )
        if (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
            or not 1 <= self.max_output_tokens <= 512
        ):
            raise DevelopmentalEvaluationError(
                "max_output_tokens must be in [1, 512]"
            )
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise DevelopmentalEvaluationError("seed must be an integer")
        object.__setattr__(self, "case_id", case_id)
        object.__setattr__(self, "prompt", prompt)
        object.__setattr__(self, "required_terms", required)
        object.__setattr__(self, "forbidden_terms", forbidden)
        object.__setattr__(self, "weight", _finite_weight(self.weight))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema_version": "skeleton.local_development_case.v1",
                "case_id": self.case_id,
                "prompt": self.prompt,
                "required_terms": list(self.required_terms),
                "forbidden_terms": list(self.forbidden_terms),
                "weight": self.weight,
                "max_output_tokens": self.max_output_tokens,
                "seed": self.seed,
            }
        )


@dataclass(frozen=True, slots=True)
class DevelopmentalEvalSuite:
    """Bounded offline suite that is explicitly not a promotion holdout."""

    suite_id: str
    cases: tuple[DevelopmentalEvalCase, ...]

    def __post_init__(self) -> None:
        suite_id = _text(self.suite_id, "suite_id", maximum=256)
        rows = tuple(self.cases)
        if not rows or len(rows) > _MAX_CASES:
            raise DevelopmentalEvaluationError(
                f"cases must contain 1..{_MAX_CASES} entries"
            )
        if any(not isinstance(item, DevelopmentalEvalCase) for item in rows):
            raise TypeError(
                "cases must contain DevelopmentalEvalCase values"
            )
        ids = [item.case_id for item in rows]
        if len(ids) != len(set(ids)):
            raise DevelopmentalEvaluationError(
                "development case ids must be unique"
            )
        digests = [item.digest for item in rows]
        if len(digests) != len(set(digests)):
            raise DevelopmentalEvaluationError(
                "development cases must be content-unique"
            )
        object.__setattr__(self, "suite_id", suite_id)
        object.__setattr__(self, "cases", rows)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema_version": "skeleton.local_development_suite.v1",
                "suite_id": self.suite_id,
                "evaluation_class": "development",
                "case_digests": [
                    item.digest
                    for item in sorted(
                        self.cases,
                        key=lambda row: row.case_id,
                    )
                ],
                "promotion_authority": False,
            }
        )


@dataclass(frozen=True, slots=True)
class DevelopmentalCaseResult:
    case_digest: str
    baseline_output_digest: str
    candidate_output_digest: str
    baseline_score: float
    candidate_score: float
    baseline_tokens: int
    candidate_tokens: int

    @property
    def gain(self) -> float:
        return self.candidate_score - self.baseline_score

    @property
    def digest(self) -> str:
        return _digest(
            {
                "case_digest": self.case_digest,
                "baseline_output_digest": self.baseline_output_digest,
                "candidate_output_digest": self.candidate_output_digest,
                "baseline_score": self.baseline_score,
                "candidate_score": self.candidate_score,
                "baseline_tokens": self.baseline_tokens,
                "candidate_tokens": self.candidate_tokens,
            }
        )


@dataclass(frozen=True, slots=True)
class DevelopmentalComparisonReport:
    suite_digest: str
    baseline_model_digest: str
    candidate_model_digest: str
    training_plan_digest: str
    method: TrainingMethod
    case_results: tuple[DevelopmentalCaseResult, ...]
    baseline_score: float
    candidate_score: float
    validation_gain: float
    compute_units: float
    attribution_verified: bool = False
    production_authority: bool = False

    def __post_init__(self) -> None:
        for field in (
            "suite_digest",
            "baseline_model_digest",
            "candidate_model_digest",
            "training_plan_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha(getattr(self, field), field),
            )
        try:
            object.__setattr__(
                self,
                "method",
                TrainingMethod(self.method),
            )
        except ValueError as exc:
            raise DevelopmentalEvaluationError(
                "unsupported training method"
            ) from exc
        if self.baseline_model_digest == self.candidate_model_digest:
            raise DevelopmentalEvaluationError(
                "developmental comparison requires distinct model identities"
            )
        if not self.case_results:
            raise DevelopmentalEvaluationError(
                "developmental comparison requires case results"
            )
        for field in (
            "baseline_score",
            "candidate_score",
            "validation_gain",
            "compute_units",
        ):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise DevelopmentalEvaluationError(
                    f"{field} must be numeric"
                )
            actual = float(value)
            if not math.isfinite(actual):
                raise DevelopmentalEvaluationError(
                    f"{field} must be finite"
                )
            object.__setattr__(self, field, actual)
        if self.compute_units <= 0.0:
            raise DevelopmentalEvaluationError(
                "compute_units must be positive"
            )
        if not isinstance(self.attribution_verified, bool):
            raise DevelopmentalEvaluationError(
                "attribution_verified must be boolean"
            )
        if self.production_authority is not False:
            raise DevelopmentalEvaluationError(
                "developmental evaluation cannot grant production authority"
            )
        expected_gain = self.candidate_score - self.baseline_score
        if abs(self.validation_gain - expected_gain) > 1e-12:
            raise DevelopmentalEvaluationError(
                "validation_gain must equal candidate minus baseline score"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema_version": "skeleton.local_development_report.v1",
                "evaluation_class": "development",
                "suite_digest": self.suite_digest,
                "baseline_model_digest": self.baseline_model_digest,
                "candidate_model_digest": self.candidate_model_digest,
                "training_plan_digest": self.training_plan_digest,
                "method": self.method.value,
                "case_result_digests": [
                    item.digest for item in self.case_results
                ],
                "baseline_score": self.baseline_score,
                "candidate_score": self.candidate_score,
                "validation_gain": self.validation_gain,
                "compute_units": self.compute_units,
                "attribution_verified": self.attribution_verified,
                "production_authority": False,
            }
        )

    def allocation_observation(self) -> MethodValidationObservation:
        if self.attribution_verified is not True:
            raise DevelopmentalEvaluationError(
                "allocator feedback requires verified training-method attribution"
            )
        return MethodValidationObservation(
            method=self.method,
            evaluation_class="development",
            validation_gain=self.validation_gain,
            compute_units=self.compute_units,
            evaluation_digest=self.digest,
            plan_digest=self.training_plan_digest,
            sample_count=len(self.case_results),
        )


def _verified_training_plan(
    plan: Mapping[str, object],
    *,
    method: TrainingMethod,
) -> str:
    if not isinstance(plan, Mapping):
        raise DevelopmentalEvaluationError(
            "candidate receipt training_plan must be a mapping"
        )
    try:
        actual_method = TrainingMethod(method)
    except ValueError as exc:
        raise DevelopmentalEvaluationError(
            "unsupported training method"
        ) from exc
    methods = plan.get("methods")
    method_counts = plan.get("method_counts")
    if not isinstance(methods, list) or not isinstance(
        method_counts,
        Mapping,
    ):
        raise DevelopmentalEvaluationError(
            "training plan lacks method evidence"
        )
    configured = {
        str(item.get("method"))
        for item in methods
        if isinstance(item, Mapping)
    }
    if actual_method.value not in configured:
        raise DevelopmentalEvaluationError(
            "attributed method is not configured in training plan"
        )
    raw_count = method_counts.get(actual_method.value, 0)
    if (
        isinstance(raw_count, bool)
        or not isinstance(raw_count, int)
        or raw_count < 1
    ):
        raise DevelopmentalEvaluationError(
            "attributed method did not materialize training documents"
        )

    payload = {
        "schema_version": "skeleton.multi_method_training_plan.v1",
        "methods": methods,
        "source_example_digests": plan.get("source_example_digests"),
        "camera_coverage_digests": plan.get("camera_coverage_digests"),
        "visual_observation_digests": plan.get(
            "visual_observation_digests"
        ),
        "efficiency_policy_digest": plan.get(
            "efficiency_policy_digest"
        ),
        "document_ids": plan.get("document_ids"),
        "corpus_digest": plan.get("corpus_digest"),
        "method_counts": dict(method_counts),
        "total_chars": plan.get("total_chars"),
        "dropped_duplicate_count": plan.get(
            "dropped_duplicate_count"
        ),
        "dropped_budget_count": plan.get("dropped_budget_count"),
    }
    claimed = _sha(plan.get("plan_digest"), "training plan digest")
    if _digest(payload) != claimed:
        raise DevelopmentalEvaluationError(
            "training plan digest does not match plan payload"
        )
    return claimed


def _score_output(text: str, case: DevelopmentalEvalCase) -> float:
    normalized = _WS.sub(" ", text.casefold().strip())
    required_hits = sum(
        1 for term in case.required_terms if term in normalized
    )
    forbidden_hits = sum(
        1 for term in case.forbidden_terms if term in normalized
    )
    required_score = required_hits / len(case.required_terms)
    forbidden_penalty = (
        0.0
        if not case.forbidden_terms
        else forbidden_hits / len(case.forbidden_terms)
    )
    return max(0.0, min(1.0, required_score - forbidden_penalty))


def evaluate_local_candidate_developmentally(
    *,
    baseline_path: str | Path,
    candidate_path: str | Path,
    suite: DevelopmentalEvalSuite,
    training_plan_digest: str,
    method: TrainingMethod,
) -> DevelopmentalComparisonReport:
    """Compare exact local model artifacts on one development-only suite."""

    if not isinstance(suite, DevelopmentalEvalSuite):
        raise TypeError("suite must be DevelopmentalEvalSuite")
    plan_digest = _sha(training_plan_digest, "training_plan_digest")
    try:
        baseline = load_local_model_artifact(baseline_path)
        candidate = load_local_model_artifact(candidate_path)
    except LocalModelArtifactError as exc:
        raise DevelopmentalEvaluationError(
            "developmental model artifact cannot be authenticated"
        ) from exc
    if baseline.receipt.model_digest == candidate.receipt.model_digest:
        raise DevelopmentalEvaluationError(
            "baseline and candidate artifacts must be distinct"
        )

    results: list[DevelopmentalCaseResult] = []
    weighted_baseline = 0.0
    weighted_candidate = 0.0
    total_weight = 0.0
    candidate_tokens = 0

    for case in sorted(suite.cases, key=lambda item: item.case_id):
        request = LocalInferenceRequest(
            prompt=case.prompt,
            instructions=(
                "Offline development evaluation. Return only learned local "
                "model output. No tools or external services."
            ),
            max_output_tokens=case.max_output_tokens,
            seed=case.seed,
        )
        baseline_result = baseline.model.infer(
            request,
            threading.Event(),
        )
        candidate_result = candidate.model.infer(
            request,
            threading.Event(),
        )
        if baseline_result.model_digest != baseline.receipt.model_digest:
            raise DevelopmentalEvaluationError(
                "baseline inference model identity drift"
            )
        if candidate_result.model_digest != candidate.receipt.model_digest:
            raise DevelopmentalEvaluationError(
                "candidate inference model identity drift"
            )
        baseline_text = baseline_result.text or ""
        candidate_text = candidate_result.text or ""
        baseline_score = _score_output(baseline_text, case)
        candidate_score = _score_output(candidate_text, case)
        weighted_baseline += baseline_score * case.weight
        weighted_candidate += candidate_score * case.weight
        total_weight += case.weight
        candidate_tokens += (
            candidate_result.input_tokens
            + candidate_result.output_tokens
        )
        results.append(
            DevelopmentalCaseResult(
                case_digest=case.digest,
                baseline_output_digest=hashlib.sha256(
                    baseline_text.encode("utf-8")
                ).hexdigest(),
                candidate_output_digest=hashlib.sha256(
                    candidate_text.encode("utf-8")
                ).hexdigest(),
                baseline_score=baseline_score,
                candidate_score=candidate_score,
                baseline_tokens=(
                    baseline_result.input_tokens
                    + baseline_result.output_tokens
                ),
                candidate_tokens=(
                    candidate_result.input_tokens
                    + candidate_result.output_tokens
                ),
            )
        )

    baseline_score = weighted_baseline / total_weight
    candidate_score = weighted_candidate / total_weight
    compute_units = max(1.0, candidate_tokens / 1000.0)
    return DevelopmentalComparisonReport(
        suite_digest=suite.digest,
        baseline_model_digest=baseline.receipt.model_digest,
        candidate_model_digest=candidate.receipt.model_digest,
        training_plan_digest=plan_digest,
        method=method,
        case_results=tuple(results),
        baseline_score=baseline_score,
        candidate_score=candidate_score,
        validation_gain=candidate_score - baseline_score,
        compute_units=compute_units,
        attribution_verified=False,
        production_authority=False,
    )


def evaluate_training_receipt_developmentally(
    *,
    baseline_path: str | Path,
    candidate_receipt: Mapping[str, object],
    suite: DevelopmentalEvalSuite,
    method: TrainingMethod,
) -> DevelopmentalComparisonReport:
    """Evaluate one exact candidate receipt with verified method attribution."""

    if not isinstance(candidate_receipt, Mapping):
        raise TypeError("candidate_receipt must be a mapping")
    plan = candidate_receipt.get("training_plan")
    if not isinstance(plan, Mapping):
        raise DevelopmentalEvaluationError(
            "candidate receipt lacks training_plan"
        )
    plan_digest = _verified_training_plan(plan, method=method)
    raw_path = candidate_receipt.get("output_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise DevelopmentalEvaluationError(
            "candidate receipt lacks output_path"
        )
    try:
        candidate = load_local_model_artifact(raw_path)
    except LocalModelArtifactError as exc:
        raise DevelopmentalEvaluationError(
            "candidate receipt artifact cannot be authenticated"
        ) from exc
    receipt_model = _sha(
        candidate_receipt.get("model_digest"),
        "candidate receipt model_digest",
    )
    receipt_artifact = _sha(
        candidate_receipt.get("artifact_sha256"),
        "candidate receipt artifact_sha256",
    )
    if candidate.receipt.model_digest != receipt_model:
        raise DevelopmentalEvaluationError(
            "candidate receipt model identity drift"
        )
    if candidate.receipt.artifact_sha256 != receipt_artifact:
        raise DevelopmentalEvaluationError(
            "candidate receipt artifact identity drift"
        )

    generic = evaluate_local_candidate_developmentally(
        baseline_path=baseline_path,
        candidate_path=raw_path,
        suite=suite,
        training_plan_digest=plan_digest,
        method=method,
    )
    return DevelopmentalComparisonReport(
        suite_digest=generic.suite_digest,
        baseline_model_digest=generic.baseline_model_digest,
        candidate_model_digest=generic.candidate_model_digest,
        training_plan_digest=generic.training_plan_digest,
        method=generic.method,
        case_results=generic.case_results,
        baseline_score=generic.baseline_score,
        candidate_score=generic.candidate_score,
        validation_gain=generic.validation_gain,
        compute_units=generic.compute_units,
        attribution_verified=True,
        production_authority=False,
    )


__all__ = [
    "DevelopmentalCaseResult",
    "DevelopmentalComparisonReport",
    "DevelopmentalEvalCase",
    "DevelopmentalEvalSuite",
    "DevelopmentalEvaluationError",
    "evaluate_local_candidate_developmentally",
    "evaluate_training_receipt_developmentally",
]
