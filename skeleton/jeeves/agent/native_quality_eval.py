"""Deterministic, payload-free quality checks for an explicitly approved GGUF.

Input cases are user/operator-provided data, not model-created quality proof.
Each case creates a fresh principal-bound native conversation and calls the
existing ExecutionSpine once. Only objective exactness and finite lexical
checks are scored; these scores do NOT prove semantic truth, safety, source
rights, physical device readiness, or release acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
import time
from typing import Any, Callable, Mapping, Sequence

from skeleton.ai.runtime.operational_ai.authority.canonical import load_json
from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import identifier, utf8
from .native_chat import NativeJeevesChat


class NativeEvaluationHold(ValueError):
    """Evaluation request or native execution violates an explicit bound."""


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    prompt: str
    exact_sha256: str | None = None
    required_terms: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    minimum_generated_tokens: int = 0
    maximum_generated_tokens: int = 8192

    def __post_init__(self) -> None:
        identifier(self.case_id, "evaluation case")
        utf8(self.prompt, maximum=32768)
        if self.exact_sha256 is not None:
            from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import identity_hash
            identity_hash(self.exact_sha256)
        if (type(self.required_terms) is not tuple
            or type(self.forbidden_terms) is not tuple
            or len(self.required_terms) > 16
            or len(self.forbidden_terms) > 16):
            raise NativeEvaluationHold("bounded required/forbidden terms required")
        for item in (*self.required_terms, *self.forbidden_terms):
            utf8(item, maximum=512)
        if (len(set(self.required_terms)) != len(self.required_terms)
            or len(set(self.forbidden_terms)) != len(self.forbidden_terms)
            or set(self.required_terms) & set(self.forbidden_terms)):
            raise NativeEvaluationHold("ambiguous or duplicate evaluation predicate")
        if not (self.exact_sha256 is not None
                or self.required_terms
                or self.forbidden_terms):
            raise NativeEvaluationHold("case requires at least one independent output predicate")
        for value in (self.minimum_generated_tokens, self.maximum_generated_tokens):
            if type(value) is not int or not 0 <= value <= 8192:
                raise NativeEvaluationHold("evaluation token bounds must be integers")
        if self.minimum_generated_tokens > self.maximum_generated_tokens:
            raise NativeEvaluationHold("evaluation token budget is inverted")


@dataclass(frozen=True, slots=True)
class EvalOutcome:
    case_id: str
    prompt_sha256: str
    output_sha256: str
    passed: bool
    exact_match: bool | None
    required_terms_satisfied: bool
    forbidden_terms_absent: bool
    generated_token_limit_satisfied: bool
    generated_tokens: int
    duration_ms: int
    model_sha256: str
    tokenizer_sha256: str

    def to_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.native_eval_outcome.v1",
            "case_id": self.case_id,
            "prompt_sha256": self.prompt_sha256,
            "output_sha256": self.output_sha256,
            "passed": self.passed,
            "exact_match": self.exact_match,
            "required_terms_satisfied": self.required_terms_satisfied,
            "forbidden_terms_absent": self.forbidden_terms_absent,
            "generated_token_limit_satisfied": self.generated_token_limit_satisfied,
            "generated_tokens": self.generated_tokens,
            "duration_ms": self.duration_ms,
            "model_sha256": self.model_sha256,
            "tokenizer_sha256": self.tokenizer_sha256,
            "semantic_truth_certified": False,
            "device_qualified": False,
            "release_certified": False,
        }


@dataclass(frozen=True, slots=True)
class EvalBudget:
    maximum_cases: int = 64
    maximum_reserved_tokens: int = 8192
    maximum_wall_seconds: float = 900

    def __post_init__(self) -> None:
        if (type(self.maximum_cases) is not int or not 1 <= self.maximum_cases <= 128
            or type(self.maximum_reserved_tokens) is not int
            or not 1 <= self.maximum_reserved_tokens <= 1000000
            or type(self.maximum_wall_seconds) not in (float, int)
            or not math.isfinite(self.maximum_wall_seconds)
            or not 0 < self.maximum_wall_seconds <= 3600):
            raise NativeEvaluationHold("invalid finite evaluation budget")


def load_evaluation_cases(raw: bytes) -> tuple[EvalCase, ...]:
    """Parse a closed, duplicate-key-free operator casebook from stdin."""
    if type(raw) is not bytes or not 1 <= len(raw) <= 262144:
        raise NativeEvaluationHold("casebook exceeds bounded UTF-8 byte ceiling")
    data = load_json(raw, ceiling=262144)
    if type(data) is not dict or set(data) != {"schema", "cases"}:
        raise NativeEvaluationHold("evaluation casebook has wrong top-level fields")
    if data["schema"] != "jeeves.native_evaluation_casebook.v1":
        raise NativeEvaluationHold("unknown evaluation casebook version")
    cases = data["cases"]
    if type(cases) is not list or not 1 <= len(cases) <= 128:
        raise NativeEvaluationHold("invalid finite evaluation case count")
    output = []
    for row in cases:
        if type(row) is not dict or not set(row) <= {
            "case_id", "prompt", "exact_sha256", "required_terms",
            "forbidden_terms", "minimum_generated_tokens",
            "maximum_generated_tokens",
        } or not {"case_id", "prompt"} <= set(row):
            raise NativeEvaluationHold("evaluation case has unknown or absent fields")
        fields = dict(row)
        for key in ("required_terms", "forbidden_terms"):
            if key in fields:
                if type(fields[key]) is not list:
                    raise NativeEvaluationHold("evaluation terms require JSON arrays")
                fields[key] = tuple(fields[key])
        try:
            output.append(EvalCase(**fields))
        except (TypeError, ValueError) as exc:
            raise NativeEvaluationHold("evaluation case violates typed contract") from exc
    if len({case.case_id for case in output}) != len(output):
        raise NativeEvaluationHold("duplicate evaluation case identity")
    return tuple(output)


def score_evaluation(case: EvalCase, *, answer: str, output_sha256: str,
                     generated_tokens: int, duration_ms: int,
                     model_sha256: str, tokenizer_sha256: str) -> EvalOutcome:
    """Deterministic criteria, never an LLM-as-judge self-report."""
    if not isinstance(case, EvalCase):
        raise NativeEvaluationHold("typed evaluation case required")
    if type(answer) is not str or not answer.strip():
        raise NativeEvaluationHold("blank answer cannot be scored")
    if type(generated_tokens) is not int or generated_tokens < 0:
        raise NativeEvaluationHold("native token count not verified")
    if type(duration_ms) is not int or duration_ms < 0:
        raise NativeEvaluationHold("nonmonotonic evaluation duration")
    if sha256(answer.encode("utf-8", "strict")).hexdigest() != output_sha256:
        raise NativeEvaluationHold("output altered after native commit")
    exact = output_sha256 == case.exact_sha256 if case.exact_sha256 is not None else None
    required = all(term in answer for term in case.required_terms)
    forbidden = all(term not in answer for term in case.forbidden_terms)
    bounded = case.minimum_generated_tokens <= generated_tokens <= case.maximum_generated_tokens
    passed = (exact is not False) and required and forbidden and bounded
    return EvalOutcome(
        case_id=case.case_id,
        prompt_sha256=sha256(case.prompt.encode("utf-8", "strict")).hexdigest(),
        output_sha256=output_sha256,
        passed=passed,
        exact_match=exact,
        required_terms_satisfied=required,
        forbidden_terms_absent=forbidden,
        generated_token_limit_satisfied=bounded,
        generated_tokens=generated_tokens,
        duration_ms=duration_ms,
        model_sha256=model_sha256,
        tokenizer_sha256=tokenizer_sha256,
    )


class NativeJeevesEvaluation:
    """One supervised native generation per independent operator-approved case.

    This has no automatic retry or batch refund. On a timeout, native
    exception, failed commit verification, or exhausted quota, evaluation
    stops. Completed cases are reported only if all enumerated cases
    produced independently confirmed native output.
    """

    def __init__(self, worker: Any, *, approved: bool,
                 budget: EvalBudget | None = None,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        if approved is not True:
            raise NativeEvaluationHold("explicit operator evaluation approval required")
        self.identity = ActiveModel.from_supervisor(worker)
        self.worker = worker
        self.budget = budget or EvalBudget()
        if not isinstance(self.budget, EvalBudget):
            raise NativeEvaluationHold("typed evaluation budget required")
        if not callable(monotonic):
            raise NativeEvaluationHold("monotonic clock required")
        self.monotonic = monotonic

    def run(self, cases: Sequence[EvalCase]) -> dict[str, object]:
        cases = tuple(cases)
        if (not 1 <= len(cases) <= self.budget.maximum_cases
            or any(not isinstance(case, EvalCase) for case in cases)
            or len({case.case_id for case in cases}) != len(cases)):
            raise NativeEvaluationHold("finite unique typed evaluation casebook required")
        # Reserve the full native output ceiling for each case *before*
        # generation. A caller cannot request unbounded quota or stealth
        # oversubscription through deceptively small expected answers.
        reserved = self.worker.spine.limits.max_output_tokens * len(cases)
        if reserved > self.budget.maximum_reserved_tokens:
            raise NativeEvaluationHold("evaluation output reservation exceeds approved ceiling")
        started = self.monotonic()
        observed = []
        for case in cases:
            if self.monotonic() - started >= self.budget.maximum_wall_seconds:
                raise NativeEvaluationHold("evaluation wall-time budget exhausted")
            before = self.monotonic()
            chat = NativeJeevesChat(self.worker)
            turn = chat.turn(case.prompt)
            after = self.monotonic()
            if (turn.model_sha256 != self.identity.model_sha256
                or turn.tokenizer_sha256 != self.identity.tokenizer_sha256):
                raise NativeEvaluationHold("native evaluation model identity changed")
            outcome = score_evaluation(
                case, answer=turn.text,
                output_sha256=turn.output_sha256,
                generated_tokens=turn.generated_tokens,
                duration_ms=max(0, int((after - before) * 1000)),
                model_sha256=turn.model_sha256,
                tokenizer_sha256=turn.tokenizer_sha256,
            )
            observed.append(outcome.to_record())
            if after - started >= self.budget.maximum_wall_seconds:
                raise NativeEvaluationHold("evaluation wall budget exhausted after native call")
        return {
            "schema": "jeeves.native_evaluation_result.v1",
            "status": "completed-source-bound-native-evaluation",
            "model_sha256": self.identity.model_sha256,
            "tokenizer_sha256": self.identity.tokenizer_sha256,
            "cases": len(observed),
            "passed": sum(1 for item in observed if item["passed"]),
            "failed": sum(1 for item in observed if not item["passed"]),
            "case_receipts": observed,
            "total_duration_ms": max(0, int((self.monotonic() - started) * 1000)),
            "semantic_truth_certified": False,
            "device_pressure_qualified": False,
            "independent_license_review": False,
            "release_certified": False,
        }


__all__ = [
    "NativeEvaluationHold", "EvalCase", "EvalOutcome", "EvalBudget",
    "load_evaluation_cases", "score_evaluation", "NativeJeevesEvaluation",
]
