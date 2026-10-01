"""Reproducible paired profiling for optional accelerators.

The profiler never selects an accelerator. It emits source/environment-bound
ProfileEvidence that the selection layer may later evaluate under policy.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import platform
import statistics
import sys
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

from skeleton.native.selection import ProfileEvidence


class AcceleratorProfilingError(RuntimeError):
    """Raised when a profile run cannot produce trustworthy evidence."""


@dataclass(frozen=True, slots=True)
class ProfileCase:
    args: tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] | None = None

    def normalized_kwargs(self) -> dict[str, Any]:
        return dict(self.kwargs or {})


@dataclass(frozen=True, slots=True)
class ProfileRun:
    evidence: ProfileEvidence
    case_count: int
    repeat_count: int
    reference_digests: tuple[str, ...]
    candidate_digests: tuple[str, ...]


def environment_id() -> str:
    """Return a deterministic, non-secret execution-environment fingerprint."""
    payload = {
        "implementation": platform.python_implementation(),
        "python": ".".join(map(str, sys.version_info[:3])),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "architecture": platform.architecture()[0],
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()[:16]
    return (
        f"{payload['system'].lower()}-"
        f"{payload['machine'].lower()}-"
        f"py{sys.version_info.major}{sys.version_info.minor}-"
        f"{digest}"
    )


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AcceleratorProfilingError(
            "profile results must be canonical-JSON serializable"
        ) from exc


def result_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _numeric_leaves(value: Any, path: str = "$") -> dict[str, float]:
    leaves: dict[str, float] = {}
    if isinstance(value, bool):
        return leaves
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            raise AcceleratorProfilingError(
                f"non-finite numeric result at {path}"
            )
        leaves[path] = number
        return leaves
    if isinstance(value, list):
        for index, item in enumerate(value):
            leaves.update(_numeric_leaves(item, f"{path}[{index}]"))
        return leaves
    if isinstance(value, tuple):
        for index, item in enumerate(value):
            leaves.update(_numeric_leaves(item, f"{path}[{index}]"))
        return leaves
    if isinstance(value, dict):
        for key in sorted(value):
            if not isinstance(key, str):
                raise AcceleratorProfilingError(
                    f"non-string mapping key at {path}"
                )
            leaves.update(_numeric_leaves(value[key], f"{path}.{key}"))
        return leaves
    return leaves


def max_abs_error(reference: Any, candidate: Any) -> float:
    """Compare JSON-shaped results and return the largest numeric error.

    Non-numeric structure must match exactly. Numeric int/float leaves may differ
    within policy tolerance and therefore are compared as finite floats.
    """
    ref_blob = _canonical_json(reference)
    cand_blob = _canonical_json(candidate)
    ref_numeric = _numeric_leaves(reference)
    cand_numeric = _numeric_leaves(candidate)

    if set(ref_numeric) != set(cand_numeric):
        return math.inf

    def scrub(value: Any, path: str = "$") -> Any:
        if path in ref_numeric:
            return "<numeric>"
        if isinstance(value, list):
            return [scrub(item, f"{path}[{index}]") for index, item in enumerate(value)]
        if isinstance(value, tuple):
            return [scrub(item, f"{path}[{index}]") for index, item in enumerate(value)]
        if isinstance(value, dict):
            return {
                key: scrub(value[key], f"{path}.{key}")
                for key in sorted(value)
            }
        return value

    if _canonical_json(scrub(reference)) != _canonical_json(scrub(candidate)):
        return math.inf
    if not ref_numeric:
        return 0.0 if ref_blob == cand_blob else math.inf
    return max(
        abs(ref_numeric[path] - cand_numeric[path])
        for path in ref_numeric
    )


def _time_call(
    func: Callable[..., Any],
    case: ProfileCase,
) -> tuple[int, Any]:
    started = time.perf_counter_ns()
    value = func(*case.args, **case.normalized_kwargs())
    elapsed = time.perf_counter_ns() - started
    return max(1, elapsed), value


def profile_pair(
    *,
    evidence_id: str,
    candidate_id: str,
    source_identity: str,
    reference: Callable[..., Any],
    candidate: Callable[..., Any],
    cases: Sequence[ProfileCase] | Iterable[ProfileCase],
    repeat_count: int = 1,
    profile_environment_id: str | None = None,
) -> ProfileRun:
    """Profile paired reference/candidate calls and emit selection evidence.

    Calls are interleaved reference->candidate per case to reduce temporal skew.
    Candidate exceptions are counted; TimeoutError is a timeout and other
    exceptions are crashes. A receipt is refused if no candidate sample succeeds.
    """
    if not callable(reference) or not callable(candidate):
        raise TypeError("reference and candidate must be callable")
    if isinstance(repeat_count, bool) or not isinstance(repeat_count, int) or repeat_count < 1:
        raise ValueError("repeat_count must be a positive integer")
    normalized_cases = tuple(cases)
    if not normalized_cases or not all(isinstance(item, ProfileCase) for item in normalized_cases):
        raise ValueError("cases must contain at least one ProfileCase")

    reference_timings: list[int] = []
    candidate_timings: list[int] = []
    reference_digests: list[str] = []
    candidate_digests: list[str] = []
    observed_error = 0.0
    correctness_passed = True
    crash_count = 0
    timeout_count = 0

    for _ in range(repeat_count):
        for case in normalized_cases:
            ref_ns, ref_value = _time_call(reference, case)
            reference_timings.append(ref_ns)
            reference_digests.append(result_digest(ref_value))
            try:
                cand_ns, cand_value = _time_call(candidate, case)
            except TimeoutError:
                timeout_count += 1
                correctness_passed = False
                continue
            except Exception:
                crash_count += 1
                correctness_passed = False
                continue

            candidate_timings.append(cand_ns)
            candidate_digests.append(result_digest(cand_value))
            error = max_abs_error(ref_value, cand_value)
            if not math.isfinite(error):
                correctness_passed = False
                observed_error = math.inf
            elif math.isfinite(observed_error):
                observed_error = max(observed_error, error)

    if not candidate_timings:
        raise AcceleratorProfilingError(
            "candidate produced no successful samples; refusing to mint profile evidence"
        )

    sample_count = len(reference_timings)
    evidence = ProfileEvidence(
        evidence_id=evidence_id,
        candidate_id=candidate_id,
        source_identity=source_identity,
        environment_id=profile_environment_id or environment_id(),
        sample_count=sample_count,
        reference_median_ns=max(1, int(statistics.median(reference_timings))),
        candidate_median_ns=max(1, int(statistics.median(candidate_timings))),
        correctness_passed=correctness_passed,
        max_abs_error=observed_error,
        crash_count=crash_count,
        timeout_count=timeout_count,
    )
    return ProfileRun(
        evidence=evidence,
        case_count=len(normalized_cases),
        repeat_count=repeat_count,
        reference_digests=tuple(reference_digests),
        candidate_digests=tuple(candidate_digests),
    )


__all__ = [
    "AcceleratorProfilingError",
    "ProfileCase",
    "ProfileRun",
    "environment_id",
    "max_abs_error",
    "profile_pair",
    "result_digest",
]
