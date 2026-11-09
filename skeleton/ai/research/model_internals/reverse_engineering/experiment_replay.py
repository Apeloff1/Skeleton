"""Deterministic replay verification for characterization protocols."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class ReplayExpectation:
    step_id: str
    input_digest: str
    expected_output_digest: str

    def __post_init__(self) -> None:
        if not self.step_id:
            raise ReverseEngineeringError("replay expectation requires step_id")
        if not is_sha256_digest(self.input_digest) or not is_sha256_digest(self.expected_output_digest):
            raise ReverseEngineeringError("replay expectation digests must be sha256 hex")


@dataclass(frozen=True)
class ReplayObservation:
    step_id: str
    actual_output_digest: str

    def __post_init__(self) -> None:
        if not self.step_id:
            raise ReverseEngineeringError("replay observation requires step_id")
        if not is_sha256_digest(self.actual_output_digest):
            raise ReverseEngineeringError("actual_output_digest must be sha256 hex")


@dataclass(frozen=True)
class ReplayVerificationReport:
    expected_step_count: int
    observed_step_count: int
    matched_step_count: int
    mismatched_step_count: int
    missing_step_ids: tuple[str, ...]
    unexpected_step_ids: tuple[str, ...]
    exact_replay: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "expected_step_count": self.expected_step_count,
            "observed_step_count": self.observed_step_count,
            "matched_step_count": self.matched_step_count,
            "mismatched_step_count": self.mismatched_step_count,
            "missing_step_ids": list(self.missing_step_ids),
            "unexpected_step_ids": list(self.unexpected_step_ids),
            "exact_replay": self.exact_replay,
            "digest": self.digest,
        }


def verify_experiment_replay(
    expectations: Sequence[ReplayExpectation],
    observations: Sequence[ReplayObservation],
) -> ReplayVerificationReport:
    if not expectations:
        raise ReverseEngineeringError("experiment replay requires expectations")
    expected_ids = [item.step_id for item in expectations]
    observed_ids = [item.step_id for item in observations]
    if len(expected_ids) != len(set(expected_ids)):
        raise ReverseEngineeringError("replay expectation ids must be unique")
    if len(observed_ids) != len(set(observed_ids)):
        raise ReverseEngineeringError("replay observation ids must be unique")

    expected = {item.step_id: item for item in expectations}
    observed = {item.step_id: item for item in observations}
    shared = sorted(set(expected) & set(observed))
    matched = sum(
        expected[step_id].expected_output_digest == observed[step_id].actual_output_digest
        for step_id in shared
    )
    mismatched = len(shared) - matched
    missing = tuple(sorted(set(expected) - set(observed)))
    unexpected = tuple(sorted(set(observed) - set(expected)))
    exact = matched == len(expectations) and not missing and not unexpected
    payload = {
        "expectations": [
            {
                "step_id": item.step_id,
                "input_digest": item.input_digest,
                "expected_output_digest": item.expected_output_digest,
            }
            for item in sorted(expectations, key=lambda value: value.step_id)
        ],
        "observations": [
            {
                "step_id": item.step_id,
                "actual_output_digest": item.actual_output_digest,
            }
            for item in sorted(observations, key=lambda value: value.step_id)
        ],
    }
    return ReplayVerificationReport(
        expected_step_count=len(expectations),
        observed_step_count=len(observations),
        matched_step_count=matched,
        mismatched_step_count=mismatched,
        missing_step_ids=missing,
        unexpected_step_ids=unexpected,
        exact_replay=exact,
        digest=stable_digest(payload),
    )
