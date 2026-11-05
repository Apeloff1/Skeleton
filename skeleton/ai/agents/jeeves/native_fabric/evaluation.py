"""Deterministic, finite native-AI quality scoring without model self-judging.

This evaluation layer can check exact hashes, schema, bounded lexical terms,
source citations and committed receipt metadata. It cannot prove physical
GGUF, semantic truth, device readiness or licensing without external evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
import re
from typing import Any, Mapping, Sequence

from .contracts import (
    ContractHold, canonical_bytes, digest, exact_integer, finite,
    fingerprint, identifier, parse_json, text,
)


@dataclass(frozen=True, slots=True)
class Predicate:
    predicate_id: str
    kind: str
    parameter: str
    expected: bool = True

    def __post_init__(self):
        identifier(self.predicate_id)
        if self.kind not in (
            "contains", "not_contains", "starts_with", "ends_with",
            "exact_sha256", "min_bytes", "max_bytes", "valid_json",
            "json_object", "json_has_key", "json_equal_literal",
            "regex_fullmatch", "ascii_only", "nonempty",
        ):
            raise ContractHold("unknown objective evaluation predicate")
        text(self.parameter, maximum_bytes=4096, may_be_empty=True)
        if type(self.expected) is not bool:
            raise ContractHold("strict predicate expectation required")
        if self.kind == "exact_sha256":
            digest(self.parameter)
        if self.kind in ("min_bytes", "max_bytes"):
            exact_integer(int(self.parameter), maximum=1048576)

    def evaluate(self, output: str) -> bool:
        text(output, maximum_bytes=1048576, may_be_empty=True)
        raw = output.encode("utf-8", "strict")
        if self.kind == "contains":
            answer = self.parameter in output
        elif self.kind == "not_contains":
            answer = self.parameter not in output
        elif self.kind == "starts_with":
            answer = output.startswith(self.parameter)
        elif self.kind == "ends_with":
            answer = output.endswith(self.parameter)
        elif self.kind == "exact_sha256":
            answer = sha256(raw).hexdigest() == self.parameter
        elif self.kind == "min_bytes":
            answer = len(raw) >= int(self.parameter)
        elif self.kind == "max_bytes":
            answer = len(raw) <= int(self.parameter)
        elif self.kind == "ascii_only":
            answer = output.isascii()
        elif self.kind == "nonempty":
            answer = bool(output.strip())
        elif self.kind == "regex_fullmatch":
            if len(self.parameter) > 256 or len(output) > 32768:
                raise ContractHold("regex input would exceed bounded evaluator")
            try:
                answer = re.fullmatch(self.parameter, output) is not None
            except re.error as exc:
                raise ContractHold("invalid evaluation regex") from exc
        else:
            try:
                parsed = parse_json(raw)
                valid = True
            except ContractHold:
                parsed, valid = None, False
            if self.kind == "valid_json":
                answer = valid
            elif self.kind == "json_object":
                answer = valid and type(parsed) is dict
            elif self.kind == "json_has_key":
                answer = valid and type(parsed) is dict and self.parameter in parsed
            else:
                key, _, expected = self.parameter.partition("=")
                answer = (
                    valid and type(parsed) is dict
                    and key in parsed and canonical_bytes(parsed[key]) == expected.encode("utf-8")
                )
        return answer is self.expected


@dataclass(frozen=True, slots=True)
class Case:
    case_id: str
    input_sha256: str
    predicates: tuple[Predicate, ...]
    maximum_output_bytes: int = 131072
    maximum_duration_ms: int = 90000
    maximum_generated_tokens: int = 8192

    def __post_init__(self):
        identifier(self.case_id, "case")
        digest(self.input_sha256)
        if type(self.predicates) is not tuple or not 1 <= len(self.predicates) <= 64:
            raise ContractHold("bounded nonempty objective predicates required")
        if any(not isinstance(x, Predicate) for x in self.predicates):
            raise ContractHold("typed predicate required")
        if len({x.predicate_id for x in self.predicates}) != len(self.predicates):
            raise ContractHold("duplicate predicate ID")
        exact_integer(self.maximum_output_bytes, minimum=1, maximum=1048576)
        exact_integer(self.maximum_duration_ms, minimum=1, maximum=600000)
        exact_integer(self.maximum_generated_tokens, minimum=1, maximum=8192)


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    passed: bool
    observed_sha256: str
    failed_predicates: tuple[str, ...]
    duration_ms: int
    generated_tokens: int
    authoritative_commit: bool

    def to_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.fabric.case_result.v1",
            "case_id": self.case_id,
            "passed": self.passed,
            "observed_sha256": self.observed_sha256,
            "failed_predicates": list(self.failed_predicates),
            "duration_ms": self.duration_ms,
            "generated_tokens": self.generated_tokens,
            "authoritative_commit": self.authoritative_commit,
            "physical_native_inference_qualified": False,
            "semantic_truth_certified": False,
        }


def evaluate_case(
    case: Case, *, answer: str,
    prompt_sha256: str, receipt_sha256: str,
    duration_ms: int, generated_tokens: int,
    authoritative_commit: bool,
) -> CaseResult:
    if not isinstance(case, Case):
        raise ContractHold("typed deterministic case required")
    digest(prompt_sha256)
    digest(receipt_sha256)
    exact_integer(duration_ms, maximum=600000)
    exact_integer(generated_tokens, maximum=8192)
    if type(authoritative_commit) is not bool:
        raise ContractHold("authoritative commit must be strict boolean")
    text(answer, maximum_bytes=1048576, may_be_empty=True)
    real_digest = sha256(answer.encode("utf-8", "strict")).hexdigest()
    if real_digest != receipt_sha256:
        raise ContractHold("answer differs from canonical output receipt")
    if case.input_sha256 != prompt_sha256:
        raise ContractHold("evaluation prompt differs from bound case")
    failures = []
    if not authoritative_commit:
        failures.append("missing_authoritative_commit")
    if len(answer.encode("utf-8")) > case.maximum_output_bytes:
        failures.append("output_budget")
    if duration_ms > case.maximum_duration_ms:
        failures.append("wall_budget")
    if generated_tokens > case.maximum_generated_tokens:
        failures.append("token_budget")
    for predicate in case.predicates:
        if not predicate.evaluate(answer):
            failures.append(predicate.predicate_id)
    return CaseResult(
        case_id=case.case_id,
        passed=not failures,
        observed_sha256=real_digest,
        failed_predicates=tuple(failures),
        duration_ms=duration_ms,
        generated_tokens=generated_tokens,
        authoritative_commit=authoritative_commit,
    )


def aggregate_results(
    results: Sequence[CaseResult], *,
    expected_case_ids: Sequence[str],
) -> dict[str, object]:
    if type(results) not in (tuple, list) or type(expected_case_ids) not in (tuple, list):
        raise ContractHold("explicit finite case collection required")
    if not 1 <= len(expected_case_ids) <= 10000:
        raise ContractHold("empty or unbounded casebook")
    required = tuple(identifier(x) for x in expected_case_ids)
    if len(set(required)) != len(required):
        raise ContractHold("duplicate casebook identity")
    observed = tuple(x.case_id for x in results)
    if any(not isinstance(x, CaseResult) for x in results):
        raise ContractHold("typed case result required")
    if len(observed) != len(set(observed)) or set(observed) != set(required):
        raise ContractHold("missing, repeated or extra case result")
    passed = sum(x.passed for x in results)
    failures = len(results) - passed
    return {
        "schema": "jeeves.fabric.quality_report.v1",
        "cases": len(required),
        "passed": passed,
        "failed": failures,
        "pass_ratio": passed / len(required),
        "case_ids": sorted(required),
        "all_authoritatively_committed": all(x.authoritative_commit for x in results),
        "source_only_metrics": True,
        "release_certified": False,
    }


__all__ = ["Predicate", "Case", "CaseResult",
           "evaluate_case", "aggregate_results"]
