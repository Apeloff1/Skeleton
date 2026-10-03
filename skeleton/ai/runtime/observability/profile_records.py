"""Immutable performance-profile evidence for the AI runtime.

The existing profilers collect measurements. This module packages those
measurements with workload/environment/phase identity so comparisons cannot
silently mix unlike runs.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Iterable


_PHASES=frozenset({"startup","steady_state","tail"})


class ProfileRecordError(ValueError):
    """A profile run, sample, or comparison invariant failed."""


def _token(name: str, value: object) -> str:
    if not isinstance(value,str) or not value or value != value.strip():
        raise ProfileRecordError(f"{name} must be non-empty normalized text")
    if len(value)>256:
        raise ProfileRecordError(f"{name} exceeds maximum length")
    return value


def _finite_nonnegative(name: str, value: object) -> float:
    if isinstance(value,bool) or not isinstance(value,(int,float)):
        raise ProfileRecordError(f"{name} must be finite and non-negative")
    result=float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ProfileRecordError(f"{name} must be finite and non-negative")
    return result


def _positive_int(name: str, value: object) -> int:
    if isinstance(value,bool) or not isinstance(value,int) or value<=0:
        raise ProfileRecordError(f"{name} must be a positive integer")
    return value


def _regression_ppm(*, baseline: float, candidate: float) -> int:
    if baseline == 0.0:
        return 0 if candidate == 0.0 else 1_000_000_000
    return round((candidate - baseline) / baseline * 1_000_000)


def _digest(value: object) -> str:
    try:
        raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    except (TypeError,ValueError) as exc:
        raise ProfileRecordError("profile evidence must be canonical JSON") from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProfileSample:
    """One normalized operation sample in a declared profile phase."""

    operation_id: str
    phase: str
    duration_ms: float
    sample_index: int

    def __post_init__(self) -> None:
        object.__setattr__(self,"operation_id",_token("operation_id",self.operation_id))
        phase=_token("phase",self.phase)
        if phase not in _PHASES:
            raise ProfileRecordError("phase must be startup, steady_state, or tail")
        object.__setattr__(self,"phase",phase)
        object.__setattr__(
            self,
            "duration_ms",
            _finite_nonnegative("duration_ms",self.duration_ms),
        )
        object.__setattr__(
            self,
            "sample_index",
            _positive_int("sample_index",self.sample_index),
        )

    @property
    def digest(self) -> str:
        return _digest({
            "operation_id":self.operation_id,
            "phase":self.phase,
            "duration_ms":self.duration_ms,
            "sample_index":self.sample_index,
        })


@dataclass(frozen=True, slots=True)
class ProfileRun:
    """Immutable bundle of comparable samples."""

    run_id: str
    workload_id: str
    environment_id: str
    operation_id: str
    phase: str
    samples: tuple[ProfileSample,...]

    def __post_init__(self) -> None:
        for name in ("run_id","workload_id","environment_id","operation_id"):
            object.__setattr__(self,name,_token(name,getattr(self,name)))
        phase=_token("phase",self.phase)
        if phase not in _PHASES:
            raise ProfileRecordError("phase must be startup, steady_state, or tail")
        object.__setattr__(self,"phase",phase)
        if not isinstance(self.samples,tuple) or not self.samples:
            raise ProfileRecordError("samples must be a non-empty immutable tuple")
        if any(not isinstance(item,ProfileSample) for item in self.samples):
            raise ProfileRecordError("samples must contain ProfileSample values")
        indexes=[item.sample_index for item in self.samples]
        if len(indexes)!=len(set(indexes)):
            raise ProfileRecordError("sample indexes must be unique")
        for item in self.samples:
            if item.operation_id != self.operation_id:
                raise ProfileRecordError("sample operation identity mismatch")
            if item.phase != self.phase:
                raise ProfileRecordError("sample phase mismatch")
        object.__setattr__(
            self,
            "samples",
            tuple(sorted(self.samples,key=lambda item:item.sample_index)),
        )

    @property
    def durations_ms(self) -> tuple[float,...]:
        return tuple(item.duration_ms for item in self.samples)

    @property
    def mean_ms(self) -> float:
        values=self.durations_ms
        return sum(values)/len(values)

    @property
    def p95_ms(self) -> float:
        values=sorted(self.durations_ms)
        return values[min(len(values)-1,int(len(values)*0.95))]

    @property
    def p99_ms(self) -> float:
        values=sorted(self.durations_ms)
        return values[min(len(values)-1,int(len(values)*0.99))]

    @property
    def digest(self) -> str:
        return _digest({
            "run_id":self.run_id,
            "workload_id":self.workload_id,
            "environment_id":self.environment_id,
            "operation_id":self.operation_id,
            "phase":self.phase,
            "sample_digests":[item.digest for item in self.samples],
        })


@dataclass(frozen=True, slots=True)
class PerformanceFinding:
    """Evidence-only comparison between identity-compatible profile runs."""

    baseline_run_digest: str
    candidate_run_digest: str
    metric: str
    baseline_value_ms: float
    candidate_value_ms: float
    regression_ppm: int
    regressed: bool

    def __post_init__(self) -> None:
        for name in ("baseline_run_digest","candidate_run_digest"):
            value=getattr(self,name)
            if (
                not isinstance(value,str)
                or len(value)!=64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise ProfileRecordError(f"{name} must be lowercase sha256")
        object.__setattr__(self,"metric",_token("metric",self.metric))
        if self.metric not in {"mean_ms","p95_ms","p99_ms"}:
            raise ProfileRecordError("metric must be mean_ms, p95_ms, or p99_ms")
        object.__setattr__(
            self,
            "baseline_value_ms",
            _finite_nonnegative("baseline_value_ms",self.baseline_value_ms),
        )
        object.__setattr__(
            self,
            "candidate_value_ms",
            _finite_nonnegative("candidate_value_ms",self.candidate_value_ms),
        )
        if isinstance(self.regression_ppm,bool) or not isinstance(self.regression_ppm,int):
            raise ProfileRecordError("regression_ppm must be integer")
        expected_ppm = _regression_ppm(
            baseline=self.baseline_value_ms,
            candidate=self.candidate_value_ms,
        )
        if self.regression_ppm != expected_ppm:
            raise ProfileRecordError(
                "regression_ppm must match baseline/candidate measurements"
            )
        if not isinstance(self.regressed,bool):
            raise ProfileRecordError("regressed must be boolean")
        if self.regressed != (self.regression_ppm > 0):
            raise ProfileRecordError("regressed state must match regression_ppm")

    @property
    def digest(self) -> str:
        return _digest({
            "baseline_run_digest":self.baseline_run_digest,
            "candidate_run_digest":self.candidate_run_digest,
            "metric":self.metric,
            "baseline_value_ms":self.baseline_value_ms,
            "candidate_value_ms":self.candidate_value_ms,
            "regression_ppm":self.regression_ppm,
            "regressed":self.regressed,
        })


def compare_profiles(
    *,
    baseline: ProfileRun,
    candidate: ProfileRun,
    metric: str,
) -> PerformanceFinding:
    if not isinstance(baseline,ProfileRun) or not isinstance(candidate,ProfileRun):
        raise TypeError("baseline and candidate must be ProfileRun")
    identity_before=(baseline.workload_id,baseline.environment_id,baseline.operation_id,baseline.phase)
    identity_after=(candidate.workload_id,candidate.environment_id,candidate.operation_id,candidate.phase)
    if identity_before != identity_after:
        raise ProfileRecordError(
            "profile comparison requires identical workload/environment/operation/phase identity"
        )
    metric_name=_token("metric",metric)
    if metric_name not in {"mean_ms","p95_ms","p99_ms"}:
        raise ProfileRecordError("metric must be mean_ms, p95_ms, or p99_ms")
    before=float(getattr(baseline,metric_name))
    after=float(getattr(candidate,metric_name))
    ppm=_regression_ppm(baseline=before,candidate=after)
    return PerformanceFinding(
        baseline_run_digest=baseline.digest,
        candidate_run_digest=candidate.digest,
        metric=metric_name,
        baseline_value_ms=before,
        candidate_value_ms=after,
        regression_ppm=ppm,
        regressed=ppm>0,
    )


__all__=[
    "PerformanceFinding",
    "ProfileRecordError",
    "ProfileRun",
    "ProfileSample",
    "compare_profiles",
]
