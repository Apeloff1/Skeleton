"""Reliability, observability and release controls for deferred AI volumes."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Iterable, Mapping

from .contracts import sha256_json


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _ratio(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be in [0, 1]")
    return number


@dataclass(frozen=True, slots=True)
class SLOSpec:
    slo_id: str
    target: float
    window_seconds: int
    indicator: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "slo_id", _text(self.slo_id, "slo_id"))
        object.__setattr__(self, "indicator", _text(self.indicator, "indicator"))
        object.__setattr__(self, "target", _ratio(self.target, "target"))
        if self.target <= 0:
            raise ValueError("SLO target must be positive")
        if isinstance(self.window_seconds, bool) or not isinstance(self.window_seconds, int) or self.window_seconds < 1:
            raise ValueError("window_seconds must be positive integer")


@dataclass(slots=True)
class ErrorBudget:
    spec: SLOSpec
    good: int = 0
    total: int = 0

    def observe(self, ok: bool) -> None:
        if not isinstance(ok, bool):
            raise TypeError("ok must be boolean")
        self.total += 1
        if ok:
            self.good += 1

    @property
    def success_ratio(self) -> float:
        return 1.0 if self.total == 0 else self.good / self.total

    @property
    def remaining(self) -> float:
        allowed_failure = 1.0 - self.spec.target
        observed_failure = 1.0 - self.success_ratio
        if allowed_failure == 0:
            return 1.0 if observed_failure == 0 else 0.0
        return max(0.0, 1.0 - observed_failure / allowed_failure)

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0.0


class CardinalityGuard:
    def __init__(self, *, max_values_per_label: int = 100) -> None:
        if isinstance(max_values_per_label, bool) or not isinstance(max_values_per_label, int) or max_values_per_label < 1:
            raise ValueError("max_values_per_label must be positive integer")
        self.max_values_per_label = max_values_per_label
        self._values: dict[str, set[str]] = {}

    def observe(self, labels: Mapping[str, str]) -> None:
        if not isinstance(labels, Mapping):
            raise TypeError("labels must be a mapping")
        for key, value in labels.items():
            key = _text(key, "label key")
            value = _text(value, "label value")
            if any(token in key.lower() for token in ("email", "token", "secret", "prompt", "content")):
                raise ValueError("sensitive/high-cardinality label key is forbidden")
            bucket = self._values.setdefault(key, set())
            if value not in bucket and len(bucket) >= self.max_values_per_label:
                raise RuntimeError(f"metric label cardinality exceeded for {key}")
            bucket.add(value)


@dataclass(frozen=True, slots=True)
class TraceSpan:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    operation: str
    started_ns: int
    ended_ns: int
    receipt_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("trace_id", "span_id", "operation"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.parent_span_id is not None:
            object.__setattr__(self, "parent_span_id", _text(self.parent_span_id, "parent_span_id"))
        for name in ("started_ns", "ended_ns"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be non-negative integer")
        if self.ended_ns < self.started_ns:
            raise ValueError("span cannot end before it starts")
        if len(self.receipt_refs) != len(set(self.receipt_refs)):
            raise ValueError("receipt refs must be unique")

    @property
    def duration_ns(self) -> int:
        return self.ended_ns - self.started_ns


class TraceModel:
    def __init__(self) -> None:
        self._spans: dict[str, TraceSpan] = {}

    def add(self, span: TraceSpan) -> None:
        if span.span_id in self._spans:
            if self._spans[span.span_id] != span:
                raise ValueError("span identity collision")
            return
        if span.parent_span_id is not None:
            parent = self._spans.get(span.parent_span_id)
            if parent is None:
                raise ValueError("parent span must be recorded first")
            if parent.trace_id != span.trace_id:
                raise ValueError("cross-trace parent is forbidden")
        self._spans[span.span_id] = span

    def ordered(self, trace_id: str) -> tuple[TraceSpan, ...]:
        return tuple(sorted(
            (span for span in self._spans.values() if span.trace_id == trace_id),
            key=lambda span: (span.started_ns, span.span_id),
        ))


@dataclass(frozen=True, slots=True)
class ProfileRecord:
    profile_id: str
    workload_digest: str
    code_digest: str
    wall_ms: float
    cpu_ms: float
    peak_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", _text(self.profile_id, "profile_id"))
        for name in ("workload_digest", "code_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64:
                raise ValueError(f"{name} must be sha256")
        for name in ("wall_ms", "cpu_ms"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if isinstance(self.peak_bytes, bool) or not isinstance(self.peak_bytes, int) or self.peak_bytes < 0:
            raise ValueError("peak_bytes must be non-negative integer")


class LatencyBudget:
    def __init__(self, total_ms: int, stages: Mapping[str, int]) -> None:
        if isinstance(total_ms, bool) or not isinstance(total_ms, int) or total_ms < 1:
            raise ValueError("total_ms must be positive integer")
        normalized: dict[str, int] = {}
        for name, value in stages.items():
            name = _text(name, "stage")
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("stage budgets must be non-negative integers")
            normalized[name] = value
        if sum(normalized.values()) > total_ms:
            raise ValueError("stage budgets oversubscribe total latency")
        self.total_ms = total_ms
        self.stages = normalized

    def remaining(self, actuals: Mapping[str, int]) -> int:
        used = 0
        for stage, value in actuals.items():
            if stage not in self.stages:
                raise KeyError(f"unknown latency stage {stage}")
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("actual latency must be non-negative integer")
            used += value
        return max(0, self.total_ms - used)


@dataclass(frozen=True, slots=True)
class EfficiencySample:
    workload_digest: str
    quality: float
    energy_joules: float
    compute_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.workload_digest, str) or len(self.workload_digest) != 64:
            raise ValueError("workload_digest must be sha256")
        object.__setattr__(self, "quality", _ratio(self.quality, "quality"))
        for name in ("energy_joules", "compute_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f"{name} must be finite and positive")

    @property
    def quality_per_joule(self) -> float:
        return self.quality / float(self.energy_joules)


@dataclass(frozen=True, slots=True)
class Fault:
    fault_id: str
    target: str
    kind: str
    bounded_seconds: int

    def __post_init__(self) -> None:
        for name in ("fault_id", "target", "kind"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if isinstance(self.bounded_seconds, bool) or not isinstance(self.bounded_seconds, int) or self.bounded_seconds < 1:
            raise ValueError("bounded_seconds must be positive integer")


@dataclass(frozen=True, slots=True)
class ChaosCampaign:
    campaign_id: str
    faults: tuple[Fault, ...]
    rollback_ref: str
    hypothesis: str = "bounded fault preserves recovery objective"
    max_affected_targets: int = 1
    max_total_fault_seconds: int = 60

    def __post_init__(self) -> None:
        object.__setattr__(self, "campaign_id", _text(self.campaign_id, "campaign_id"))
        object.__setattr__(self, "rollback_ref", _text(self.rollback_ref, "rollback_ref"))
        object.__setattr__(self, "hypothesis", _text(self.hypothesis, "hypothesis"))
        ids = [fault.fault_id for fault in self.faults]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("chaos campaign needs unique faults")
        for name in ("max_affected_targets", "max_total_fault_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be positive integer")
        if len({fault.target for fault in self.faults}) > self.max_affected_targets:
            raise ValueError("chaos campaign exceeds target blast radius")
        if sum(fault.bounded_seconds for fault in self.faults) > self.max_total_fault_seconds:
            raise ValueError("chaos campaign exceeds fault-time budget")

    @property
    def digest(self) -> str:
        return sha256_json({
            "campaign_id": self.campaign_id,
            "hypothesis": self.hypothesis,
            "rollback_ref": self.rollback_ref,
            "max_affected_targets": self.max_affected_targets,
            "max_total_fault_seconds": self.max_total_fault_seconds,
            "faults": [
                {
                    "fault_id": fault.fault_id,
                    "target": fault.target,
                    "kind": fault.kind,
                    "bounded_seconds": fault.bounded_seconds,
                }
                for fault in self.faults
            ],
        })


@dataclass(frozen=True, slots=True)
class ChaosAuthority:
    principal_id: str
    allowed_targets: tuple[str, ...]
    allowed_fault_kinds: tuple[str, ...]
    max_fault_seconds: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "principal_id", _text(self.principal_id, "principal_id"))
        if not self.allowed_targets or len(self.allowed_targets) != len(set(self.allowed_targets)):
            raise ValueError("allowed_targets must be unique and non-empty")
        if not self.allowed_fault_kinds or len(self.allowed_fault_kinds) != len(set(self.allowed_fault_kinds)):
            raise ValueError("allowed_fault_kinds must be unique and non-empty")
        if isinstance(self.max_fault_seconds, bool) or not isinstance(self.max_fault_seconds, int) or self.max_fault_seconds < 1:
            raise ValueError("max_fault_seconds must be positive integer")

    def authorize(self, campaign: ChaosCampaign) -> None:
        for fault in campaign.faults:
            if fault.target not in self.allowed_targets:
                raise PermissionError(f"chaos target not authorized: {fault.target}")
            if fault.kind not in self.allowed_fault_kinds:
                raise PermissionError(f"chaos fault kind not authorized: {fault.kind}")
            if fault.bounded_seconds > self.max_fault_seconds:
                raise PermissionError(f"chaos fault duration not authorized: {fault.fault_id}")


@dataclass(frozen=True, slots=True)
class ChaosObservation:
    campaign_id: str
    observed_at: int
    healthy: bool
    error_budget_remaining: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "campaign_id", _text(self.campaign_id, "campaign_id"))
        if isinstance(self.observed_at, bool) or not isinstance(self.observed_at, int) or self.observed_at < 0:
            raise ValueError("observed_at must be non-negative integer")
        if not isinstance(self.healthy, bool):
            raise TypeError("healthy must be boolean")
        object.__setattr__(self, "error_budget_remaining", _ratio(self.error_budget_remaining, "error_budget_remaining"))


@dataclass(frozen=True, slots=True)
class ChaosReceipt:
    campaign_digest: str
    principal_id: str
    decision: str
    observation_digest: str
    rollback_ref: str

    def __post_init__(self) -> None:
        for name in ("campaign_digest", "observation_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64:
                raise ValueError(f"{name} must be sha256")
        object.__setattr__(self, "principal_id", _text(self.principal_id, "principal_id"))
        object.__setattr__(self, "rollback_ref", _text(self.rollback_ref, "rollback_ref"))
        if self.decision not in {"continue", "abort"}:
            raise ValueError("decision must be continue or abort")

    @property
    def digest(self) -> str:
        return sha256_json({
            "campaign_digest": self.campaign_digest,
            "principal_id": self.principal_id,
            "decision": self.decision,
            "observation_digest": self.observation_digest,
            "rollback_ref": self.rollback_ref,
        })


class ChaosController:
    """Admission and abort boundary. It never injects faults itself."""

    def __init__(self, *, minimum_error_budget: float = 0.25) -> None:
        self.minimum_error_budget = _ratio(minimum_error_budget, "minimum_error_budget")
        self._decisions: dict[str, str] = {}

    def evaluate(
        self,
        campaign: ChaosCampaign,
        authority: ChaosAuthority,
        observation: ChaosObservation,
    ) -> ChaosReceipt:
        if observation.campaign_id != campaign.campaign_id:
            raise ValueError("observation campaign mismatch")
        authority.authorize(campaign)
        decision = (
            "continue"
            if observation.healthy and observation.error_budget_remaining >= self.minimum_error_budget
            else "abort"
        )
        observation_digest = sha256_json({
            "campaign_id": observation.campaign_id,
            "observed_at": observation.observed_at,
            "healthy": observation.healthy,
            "error_budget_remaining": observation.error_budget_remaining,
        })
        receipt = ChaosReceipt(
            campaign_digest=campaign.digest,
            principal_id=authority.principal_id,
            decision=decision,
            observation_digest=observation_digest,
            rollback_ref=campaign.rollback_ref,
        )
        prior = self._decisions.get(campaign.digest)
        if prior is not None and prior != receipt.digest:
            raise ValueError("non-deterministic chaos decision replay")
        self._decisions[campaign.digest] = receipt.digest
        return receipt


@dataclass(frozen=True, slots=True)
class RecoveryObjective:
    max_recovery_seconds: int
    max_data_loss_units: int

    def __post_init__(self) -> None:
        for name in ("max_recovery_seconds", "max_data_loss_units"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be non-negative integer")


@dataclass(frozen=True, slots=True)
class RecoveryDrill:
    drill_id: str
    campaign_id: str
    recovery_seconds: int
    data_loss_units: int
    passed: bool

    def __post_init__(self) -> None:
        for name in ("drill_id", "campaign_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("recovery_seconds", "data_loss_units"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be non-negative integer")
        if not isinstance(self.passed, bool):
            raise TypeError("passed must be boolean")

    def verify(self, objective: RecoveryObjective) -> bool:
        measured = (
            self.recovery_seconds <= objective.max_recovery_seconds
            and self.data_loss_units <= objective.max_data_loss_units
        )
        if self.passed != measured:
            raise ValueError("recovery drill pass claim disagrees with measured objective")
        return measured


@dataclass(frozen=True, slots=True)
class ReleaseRequirement:
    gate_id: str
    required: bool = True
    release_classes: tuple[str, ...] = ("default",)

    def __post_init__(self) -> None:
        object.__setattr__(self, "gate_id", _text(self.gate_id, "gate_id"))
        if not isinstance(self.required, bool):
            raise TypeError("required must be boolean")
        normalized = tuple(_text(item, "release_class") for item in self.release_classes)
        if not normalized or len(normalized) != len(set(normalized)):
            raise ValueError("release_classes must be unique and non-empty")
        object.__setattr__(self, "release_classes", normalized)


@dataclass(frozen=True, slots=True)
class ReleaseWaiver:
    gate_id: str
    release_class: str
    evidence_digest: str
    approver: str
    expires_at: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "gate_id", _text(self.gate_id, "gate_id"))
        object.__setattr__(self, "release_class", _text(self.release_class, "release_class"))
        object.__setattr__(self, "approver", _text(self.approver, "approver"))
        if not isinstance(self.evidence_digest, str) or len(self.evidence_digest) != 64:
            raise ValueError("evidence_digest must be sha256")
        if isinstance(self.expires_at, bool) or not isinstance(self.expires_at, int) or self.expires_at < 1:
            raise ValueError("expires_at must be positive integer")

    def applies(self, gate_id: str, release_class: str, now: int) -> bool:
        return (
            self.gate_id == gate_id
            and self.release_class == release_class
            and now < self.expires_at
        )


@dataclass(frozen=True, slots=True)
class QualificationDecision:
    release_id: str
    release_class: str
    qualified: bool
    blockers: tuple[str, ...]
    waived_gates: tuple[str, ...]
    input_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "release_id", _text(self.release_id, "release_id"))
        object.__setattr__(self, "release_class", _text(self.release_class, "release_class"))
        if not isinstance(self.qualified, bool):
            raise TypeError("qualified must be boolean")
        if len(self.blockers) != len(set(self.blockers)):
            raise ValueError("blockers must be unique")
        if len(self.waived_gates) != len(set(self.waived_gates)):
            raise ValueError("waived_gates must be unique")
        if not isinstance(self.input_digest, str) or len(self.input_digest) != 64:
            raise ValueError("input_digest must be sha256")


class ReleaseQualification:
    _TERMINAL_SUCCESS = "success"

    def __init__(self, requirements: Iterable[ReleaseRequirement]) -> None:
        reqs = tuple(requirements)
        ids = [item.gate_id for item in reqs]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("release gate ids must be unique and non-empty")
        self.requirements = reqs

    def _required_for(self, release_class: str) -> tuple[ReleaseRequirement, ...]:
        release_class = _text(release_class, "release_class")
        return tuple(
            req for req in self.requirements
            if req.required and release_class in req.release_classes
        )

    def qualify(self, conclusions: Mapping[str, str]) -> tuple[bool, tuple[str, ...]]:
        blockers = []
        for req in self.requirements:
            conclusion = conclusions.get(req.gate_id)
            if req.required and conclusion != self._TERMINAL_SUCCESS:
                blockers.append(f"{req.gate_id}:{conclusion or 'missing'}")
        return (not blockers, tuple(sorted(blockers)))

    def decide(
        self,
        *,
        release_id: str,
        release_class: str,
        conclusions: Mapping[str, str],
        now: int,
        waivers: Iterable[ReleaseWaiver] = (),
    ) -> QualificationDecision:
        release_id = _text(release_id, "release_id")
        release_class = _text(release_class, "release_class")
        if isinstance(now, bool) or not isinstance(now, int) or now < 0:
            raise ValueError("now must be non-negative integer")
        if not isinstance(conclusions, Mapping):
            raise TypeError("conclusions must be a mapping")

        required = self._required_for(release_class)
        if not required:
            raise ValueError(f"no release requirements declared for class {release_class}")

        waiver_rows = tuple(waivers)
        waiver_by_gate: dict[str, ReleaseWaiver] = {}
        for waiver in waiver_rows:
            if not isinstance(waiver, ReleaseWaiver):
                raise TypeError("waivers must contain ReleaseWaiver")
            if waiver.release_class != release_class:
                raise ValueError("cross-class release waiver is forbidden")
            if waiver.gate_id in waiver_by_gate:
                raise ValueError("duplicate release waiver")
            waiver_by_gate[waiver.gate_id] = waiver

        blockers: list[str] = []
        waived: list[str] = []
        normalized: dict[str, str] = {}
        for req in required:
            raw = conclusions.get(req.gate_id)
            conclusion = raw.strip().lower() if isinstance(raw, str) and raw.strip() else "missing"
            normalized[req.gate_id] = conclusion
            if conclusion == self._TERMINAL_SUCCESS:
                continue
            waiver = waiver_by_gate.get(req.gate_id)
            if waiver is not None and waiver.applies(req.gate_id, release_class, now):
                waived.append(req.gate_id)
                continue
            blockers.append(f"{req.gate_id}:{conclusion}")

        unknown_waivers = sorted(set(waiver_by_gate) - {req.gate_id for req in required})
        if unknown_waivers:
            raise ValueError("waiver targets non-required gate: " + ",".join(unknown_waivers))

        input_digest = sha256_json({
            "release_id": release_id,
            "release_class": release_class,
            "required_gates": [req.gate_id for req in required],
            "conclusions": normalized,
            "waivers": [
                {
                    "gate_id": waiver.gate_id,
                    "release_class": waiver.release_class,
                    "evidence_digest": waiver.evidence_digest,
                    "approver": waiver.approver,
                    "expires_at": waiver.expires_at,
                }
                for waiver in sorted(waiver_rows, key=lambda item: item.gate_id)
            ],
            "now": now,
        })
        return QualificationDecision(
            release_id=release_id,
            release_class=release_class,
            qualified=not blockers,
            blockers=tuple(sorted(blockers)),
            waived_gates=tuple(sorted(waived)),
            input_digest=input_digest,
        )


@dataclass(frozen=True, slots=True)
class CanaryObservation:
    sample_size: int
    error_rate: float
    quality_score: float
    latency_ratio: float

    def __post_init__(self) -> None:
        if isinstance(self.sample_size, bool) or not isinstance(self.sample_size, int) or self.sample_size < 1:
            raise ValueError("sample_size must be positive integer")
        object.__setattr__(self, "error_rate", _ratio(self.error_rate, "error_rate"))
        object.__setattr__(self, "quality_score", _ratio(self.quality_score, "quality_score"))
        if isinstance(self.latency_ratio, bool) or not isinstance(self.latency_ratio, (int, float)) or not math.isfinite(float(self.latency_ratio)) or float(self.latency_ratio) < 0:
            raise ValueError("latency_ratio must be finite and non-negative")


class CanaryController:
    def __init__(self, *, min_samples: int, max_error_rate: float, min_quality: float, max_latency_ratio: float) -> None:
        if isinstance(min_samples, bool) or not isinstance(min_samples, int) or min_samples < 1:
            raise ValueError("min_samples must be positive integer")
        self.min_samples = min_samples
        self.max_error_rate = _ratio(max_error_rate, "max_error_rate")
        self.min_quality = _ratio(min_quality, "min_quality")
        if not math.isfinite(float(max_latency_ratio)) or max_latency_ratio <= 0:
            raise ValueError("max_latency_ratio must be positive")
        self.max_latency_ratio = float(max_latency_ratio)

    def decide(self, observation: CanaryObservation) -> str:
        if observation.sample_size < self.min_samples:
            return "hold"
        if observation.error_rate > self.max_error_rate:
            return "rollback"
        if observation.quality_score < self.min_quality:
            return "rollback"
        if observation.latency_ratio > self.max_latency_ratio:
            return "rollback"
        return "promote"


@dataclass(frozen=True, slots=True)
class FeatureFlag:
    flag_id: str
    enabled: bool
    expires_at: int
    security_sensitive: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "flag_id", _text(self.flag_id, "flag_id"))
        if not isinstance(self.enabled, bool) or not isinstance(self.security_sensitive, bool):
            raise TypeError("flag booleans must be boolean")
        if isinstance(self.expires_at, bool) or not isinstance(self.expires_at, int) or self.expires_at < 1:
            raise ValueError("expires_at must be positive integer")

    def effective(self, now: int) -> bool:
        if isinstance(now, bool) or not isinstance(now, int) or now < 0:
            raise ValueError("now must be non-negative integer")
        if now >= self.expires_at:
            return False
        return self.enabled


@dataclass(frozen=True, slots=True)
class FeatureFlagAuthority:
    principal_id: str
    mutable_flags: tuple[str, ...]
    may_enable_security_sensitive: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "principal_id", _text(self.principal_id, "principal_id"))
        if not self.mutable_flags or len(self.mutable_flags) != len(set(self.mutable_flags)):
            raise ValueError("mutable_flags must be unique and non-empty")
        if not isinstance(self.may_enable_security_sensitive, bool):
            raise TypeError("may_enable_security_sensitive must be boolean")

    def authorize(self, flag: FeatureFlag, *, enable: bool) -> None:
        if not isinstance(enable, bool):
            raise TypeError("enable must be boolean")
        if flag.flag_id not in self.mutable_flags:
            raise PermissionError("feature flag is outside principal authority")
        if enable and flag.security_sensitive and not self.may_enable_security_sensitive:
            raise PermissionError("security-sensitive feature flag enable is not authorized")


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    release_id: str
    reversible: bool
    data_compatible: bool
    external_effects_reconciled: bool
    steps: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "release_id", _text(self.release_id, "release_id"))
        for name in ("reversible", "data_compatible", "external_effects_reconciled"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be boolean")
        normalized = tuple(_text(step, "rollback step") for step in self.steps)
        if not normalized or len(normalized) != len(set(normalized)):
            raise ValueError("rollback plan needs unique non-empty steps")
        object.__setattr__(self, "steps", normalized)

    @property
    def safe(self) -> bool:
        return self.reversible and self.data_compatible and self.external_effects_reconciled

    @property
    def digest(self) -> str:
        return sha256_json({
            "release_id": self.release_id,
            "reversible": self.reversible,
            "data_compatible": self.data_compatible,
            "external_effects_reconciled": self.external_effects_reconciled,
            "steps": list(self.steps),
        })


@dataclass(frozen=True, slots=True)
class DeploymentReceipt:
    release_id: str
    canary_decision: str
    rollback_digest: str
    flag_id: str | None
    flag_effective: bool
    decision: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "release_id", _text(self.release_id, "release_id"))
        if self.canary_decision not in {"hold", "rollback", "promote"}:
            raise ValueError("unknown canary decision")
        if not isinstance(self.rollback_digest, str) or len(self.rollback_digest) != 64:
            raise ValueError("rollback_digest must be sha256")
        if self.flag_id is not None:
            object.__setattr__(self, "flag_id", _text(self.flag_id, "flag_id"))
        if not isinstance(self.flag_effective, bool):
            raise TypeError("flag_effective must be boolean")
        if self.decision not in {"hold", "rollback", "promote"}:
            raise ValueError("unknown deployment decision")

    @property
    def digest(self) -> str:
        return sha256_json({
            "release_id": self.release_id,
            "canary_decision": self.canary_decision,
            "rollback_digest": self.rollback_digest,
            "flag_id": self.flag_id,
            "flag_effective": self.flag_effective,
            "decision": self.decision,
        })


class DeploymentSafety:
    """Couples canary promotion to rollback preflight and optional flag authority."""

    @staticmethod
    def decide(
        *,
        release_id: str,
        canary: CanaryController,
        observation: CanaryObservation,
        rollback: RollbackPlan,
        now: int,
        flag: FeatureFlag | None = None,
        flag_authority: FeatureFlagAuthority | None = None,
    ) -> DeploymentReceipt:
        release_id = _text(release_id, "release_id")
        if rollback.release_id != release_id:
            raise ValueError("rollback plan release mismatch")
        canary_decision = canary.decide(observation)
        if canary_decision == "rollback":
            decision = "rollback"
        elif not rollback.safe:
            decision = "hold"
        else:
            decision = canary_decision

        flag_id: str | None = None
        flag_effective = False
        if flag is not None:
            if flag_authority is None:
                raise PermissionError("feature flag mutation requires explicit authority")
            flag_authority.authorize(flag, enable=flag.enabled)
            flag_id = flag.flag_id
            flag_effective = flag.effective(now)
            if flag.enabled and not flag_effective and decision == "promote":
                decision = "hold"

        return DeploymentReceipt(
            release_id=release_id,
            canary_decision=canary_decision,
            rollback_digest=rollback.digest,
            flag_id=flag_id,
            flag_effective=flag_effective,
            decision=decision,
        )


@dataclass(slots=True)
class RetryBudget:
    max_attempts: int
    attempts: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int) or self.max_attempts < 1:
            raise ValueError("max_attempts must be positive integer")

    def consume(self) -> int:
        if self.attempts >= self.max_attempts:
            raise RuntimeError("retry budget exhausted")
        self.attempts += 1
        return self.attempts


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(slots=True)
class CircuitBreaker:
    failure_threshold: int
    success_threshold: int = 1
    state: CircuitState = CircuitState.CLOSED
    failures: int = 0
    successes: int = 0

    def __post_init__(self) -> None:
        for name in ("failure_threshold", "success_threshold"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be positive integer")

    def allow(self) -> bool:
        return self.state is not CircuitState.OPEN

    def record_failure(self) -> None:
        self.failures += 1
        self.successes = 0
        if self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def probe(self) -> None:
        if self.state is CircuitState.OPEN:
            self.state = CircuitState.HALF_OPEN
            self.failures = 0
            self.successes = 0

    def record_success(self) -> None:
        if self.state is CircuitState.HALF_OPEN:
            self.successes += 1
            if self.successes >= self.success_threshold:
                self.state = CircuitState.CLOSED
                self.failures = 0
                self.successes = 0
        elif self.state is CircuitState.CLOSED:
            self.failures = 0


@dataclass(slots=True)
class Bulkhead:
    capacity: int
    in_flight: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.capacity, bool) or not isinstance(self.capacity, int) or self.capacity < 1:
            raise ValueError("capacity must be positive integer")

    def acquire(self) -> None:
        if self.in_flight >= self.capacity:
            raise RuntimeError("bulkhead capacity exhausted")
        self.in_flight += 1

    def release(self) -> None:
        if self.in_flight <= 0:
            raise RuntimeError("bulkhead release underflow")
        self.in_flight -= 1


class CongestionController:
    def __init__(self, *, soft_limit: int, hard_limit: int) -> None:
        if not 0 <= soft_limit < hard_limit:
            raise ValueError("require 0 <= soft_limit < hard_limit")
        self.soft_limit = soft_limit
        self.hard_limit = hard_limit

    def action(self, depth: int) -> str:
        if isinstance(depth, bool) or not isinstance(depth, int) or depth < 0:
            raise ValueError("depth must be non-negative integer")
        if depth >= self.hard_limit:
            return "shed"
        if depth >= self.soft_limit:
            return "throttle"
        return "admit"


@dataclass(frozen=True, slots=True)
class DeadLetter:
    message_id: str
    reason: str
    payload_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "message_id", _text(self.message_id, "message_id"))
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        if not isinstance(self.payload_digest, str) or len(self.payload_digest) != 64:
            raise ValueError("payload_digest must be sha256")


class DeadLetterQueue:
    def __init__(self) -> None:
        self._items: dict[str, DeadLetter] = {}

    def put(self, item: DeadLetter) -> None:
        prior = self._items.get(item.message_id)
        if prior is not None and prior != item:
            raise ValueError("dead-letter identity collision")
        self._items[item.message_id] = item

    def replay(self, message_id: str) -> DeadLetter:
        try:
            return self._items.pop(message_id)
        except KeyError as exc:
            raise KeyError("unknown dead-letter message") from exc


class OperationReplayLedger:
    def __init__(self) -> None:
        self._receipts: dict[str, str] = {}

    def accept(self, operation_id: str, payload: Mapping[str, object]) -> str:
        operation_id = _text(operation_id, "operation_id")
        digest = sha256_json(dict(payload))
        prior = self._receipts.get(operation_id)
        if prior is not None:
            if prior != digest:
                raise ValueError("operation replay identity collision")
            return prior
        self._receipts[operation_id] = digest
        return digest


@dataclass(frozen=True, slots=True)
class DeterminismEnvelope:
    seed: int
    code_digest: str
    config_digest: str
    input_digest: str

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("seed must be integer")
        for name in ("code_digest", "config_digest", "input_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64:
                raise ValueError(f"{name} must be sha256")

    @property
    def digest(self) -> str:
        return sha256_json({
            "seed": self.seed,
            "code_digest": self.code_digest,
            "config_digest": self.config_digest,
            "input_digest": self.input_digest,
        })


@dataclass(slots=True)
class LogicalClock:
    value: int = 0

    def tick(self) -> int:
        self.value += 1
        return self.value

    def merge(self, remote: int) -> int:
        if isinstance(remote, bool) or not isinstance(remote, int) or remote < 0:
            raise ValueError("remote clock must be non-negative integer")
        self.value = max(self.value, remote) + 1
        return self.value
