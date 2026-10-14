"""Quality-normalized compute/energy efficiency evidence.

Efficiency claims are valid only when benchmark protocol, workload, quality
evidence, and reliability evidence are equivalent. This module records claims;
it does not tune capacity, route traffic, or change model behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math


class EfficiencyMetricError(ValueError):
    """An efficiency observation or claim invariant failed."""


def _token(name: str, value: object) -> str:
    if not isinstance(value,str) or not value or value != value.strip():
        raise EfficiencyMetricError(f"{name} must be non-empty normalized text")
    if len(value)>256:
        raise EfficiencyMetricError(f"{name} exceeds maximum length")
    return value


def _positive(name: str, value: object) -> float:
    if isinstance(value,bool) or not isinstance(value,(int,float)):
        raise EfficiencyMetricError(f"{name} must be finite and positive")
    result=float(value)
    if not math.isfinite(result) or result<=0.0:
        raise EfficiencyMetricError(f"{name} must be finite and positive")
    return result


def _sha256(name: str, value: object) -> str:
    if (
        not isinstance(value,str)
        or len(value)!=64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise EfficiencyMetricError(f"{name} must be lowercase sha256")
    return value


def _digest(value: object) -> str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ComputeObservation:
    observation_id: str
    workload_id: str
    protocol_id: str
    hardware_id: str
    work_units: float
    compute_seconds: float
    energy_joules: float
    quality_digest: str
    reliability_digest: str

    def __post_init__(self) -> None:
        for name in ("observation_id","workload_id","protocol_id","hardware_id"):
            object.__setattr__(self,name,_token(name,getattr(self,name)))
        for name in ("work_units","compute_seconds","energy_joules"):
            object.__setattr__(self,name,_positive(name,getattr(self,name)))
        object.__setattr__(
            self,
            "quality_digest",
            _sha256("quality_digest",self.quality_digest),
        )
        object.__setattr__(
            self,
            "reliability_digest",
            _sha256("reliability_digest",self.reliability_digest),
        )

    @property
    def compute_seconds_per_unit(self) -> float:
        return self.compute_seconds/self.work_units

    @property
    def energy_joules_per_unit(self) -> float:
        return self.energy_joules/self.work_units

    @property
    def digest(self) -> str:
        return _digest({
            "observation_id":self.observation_id,
            "workload_id":self.workload_id,
            "protocol_id":self.protocol_id,
            "hardware_id":self.hardware_id,
            "work_units":self.work_units,
            "compute_seconds":self.compute_seconds,
            "energy_joules":self.energy_joules,
            "quality_digest":self.quality_digest,
            "reliability_digest":self.reliability_digest,
        })


@dataclass(frozen=True, slots=True)
class EfficiencyMetric:
    observation_digest: str
    compute_seconds_per_unit: float
    energy_joules_per_unit: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observation_digest",
            _sha256("observation_digest",self.observation_digest),
        )
        object.__setattr__(
            self,
            "compute_seconds_per_unit",
            _positive("compute_seconds_per_unit",self.compute_seconds_per_unit),
        )
        object.__setattr__(
            self,
            "energy_joules_per_unit",
            _positive("energy_joules_per_unit",self.energy_joules_per_unit),
        )

    @property
    def digest(self) -> str:
        return _digest({
            "observation_digest":self.observation_digest,
            "compute_seconds_per_unit":self.compute_seconds_per_unit,
            "energy_joules_per_unit":self.energy_joules_per_unit,
        })


@dataclass(frozen=True, slots=True)
class EfficiencyClaim:
    baseline_observation_digest: str
    candidate_observation_digest: str
    compute_improvement_ppm: int
    energy_improvement_ppm: int
    quality_equivalent: bool
    reliability_equivalent: bool
    valid: bool

    def __post_init__(self) -> None:
        for name in ("baseline_observation_digest","candidate_observation_digest"):
            object.__setattr__(self,name,_sha256(name,getattr(self,name)))
        for name in ("compute_improvement_ppm","energy_improvement_ppm"):
            value=getattr(self,name)
            if isinstance(value,bool) or not isinstance(value,int):
                raise EfficiencyMetricError(f"{name} must be integer")
        for name in ("quality_equivalent","reliability_equivalent","valid"):
            if not isinstance(getattr(self,name),bool):
                raise EfficiencyMetricError(f"{name} must be boolean")
        expected_valid=(
            self.quality_equivalent
            and self.reliability_equivalent
            and (
                self.compute_improvement_ppm>0
                or self.energy_improvement_ppm>0
            )
        )
        if self.valid != expected_valid:
            raise EfficiencyMetricError(
                "valid efficiency claim must match quality/reliability equivalence and improvement evidence"
            )

    @property
    def digest(self) -> str:
        return _digest({
            "baseline_observation_digest":self.baseline_observation_digest,
            "candidate_observation_digest":self.candidate_observation_digest,
            "compute_improvement_ppm":self.compute_improvement_ppm,
            "energy_improvement_ppm":self.energy_improvement_ppm,
            "quality_equivalent":self.quality_equivalent,
            "reliability_equivalent":self.reliability_equivalent,
            "valid":self.valid,
        })


def metric_for(observation: ComputeObservation) -> EfficiencyMetric:
    if not isinstance(observation,ComputeObservation):
        raise TypeError("observation must be ComputeObservation")
    return EfficiencyMetric(
        observation_digest=observation.digest,
        compute_seconds_per_unit=observation.compute_seconds_per_unit,
        energy_joules_per_unit=observation.energy_joules_per_unit,
    )


def _improvement_ppm(*, baseline: float, candidate: float) -> int:
    return round((baseline-candidate)/baseline*1_000_000)


def compare_efficiency(
    *,
    baseline: ComputeObservation,
    candidate: ComputeObservation,
) -> EfficiencyClaim:
    if not isinstance(baseline,ComputeObservation) or not isinstance(candidate,ComputeObservation):
        raise TypeError("baseline and candidate must be ComputeObservation")
    if baseline.workload_id != candidate.workload_id:
        raise EfficiencyMetricError("efficiency comparison requires identical workload")
    if baseline.protocol_id != candidate.protocol_id:
        raise EfficiencyMetricError("efficiency comparison requires identical benchmark protocol")
    if baseline.work_units != candidate.work_units:
        raise EfficiencyMetricError("efficiency comparison requires identical work-unit count")

    quality_equivalent=baseline.quality_digest==candidate.quality_digest
    reliability_equivalent=baseline.reliability_digest==candidate.reliability_digest
    compute_ppm=_improvement_ppm(
        baseline=baseline.compute_seconds_per_unit,
        candidate=candidate.compute_seconds_per_unit,
    )
    energy_ppm=_improvement_ppm(
        baseline=baseline.energy_joules_per_unit,
        candidate=candidate.energy_joules_per_unit,
    )
    valid=(
        quality_equivalent
        and reliability_equivalent
        and (compute_ppm>0 or energy_ppm>0)
    )
    return EfficiencyClaim(
        baseline_observation_digest=baseline.digest,
        candidate_observation_digest=candidate.digest,
        compute_improvement_ppm=compute_ppm,
        energy_improvement_ppm=energy_ppm,
        quality_equivalent=quality_equivalent,
        reliability_equivalent=reliability_equivalent,
        valid=valid,
    )


__all__=[
    "ComputeObservation",
    "EfficiencyClaim",
    "EfficiencyMetric",
    "EfficiencyMetricError",
    "compare_efficiency",
    "metric_for",
]
