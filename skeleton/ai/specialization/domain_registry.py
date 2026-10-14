"""Deterministic, fail-closed specialist routing for VOL-071.

Models may propose specialist candidates. This module decides whether a specialist
is eligible to serve a domain request. Promotion requires a declared domain
profile, independently owned evaluation evidence, bounded evaluation freshness,
required source/tool coverage, no forbidden assumptions, and calibrated
confidence. Otherwise the caller receives an explicit general-capability
fallback rather than silent specialist use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import math
import re
from pathlib import Path
from typing import Iterable, Mapping

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:/-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_COLLECTION = 128
_MAX_TEXT = 2048


class SpecializationError(ValueError):
    """A specialized-intelligence contract failed closed."""


class RoutingDecision(str, Enum):
    SPECIALIST = "specialist"
    GENERAL_FALLBACK = "general_fallback"


def _identifier(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise SpecializationError(f"{field} must be a canonical lowercase identifier")
    return value


def _bounded_text(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpecializationError(f"{field} must be non-empty")
    if len(value) > _MAX_TEXT:
        raise SpecializationError(f"{field} exceeds bounded length")
    return value.strip()


def _token_set(values: Iterable[str], *, field: str) -> tuple[str, ...]:
    items = tuple(values)
    if len(items) > _MAX_COLLECTION:
        raise SpecializationError(f"{field} exceeds bounded cardinality")
    if len(items) != len(set(items)):
        raise SpecializationError(f"{field} contains duplicates")
    for item in items:
        _identifier(item, field=field)
    return tuple(sorted(items))


def _score(value: float, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpecializationError(f"{field} must be numeric")
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise SpecializationError(f"{field} must be finite and within [0, 1]")
    return value


def _timestamp(value: str, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise SpecializationError(f"{field} must be a non-empty RFC3339 timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise SpecializationError(f"{field} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise SpecializationError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _canonical_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise SpecializationError("routing time must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _digest_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class EvaluationOwnership:
    owner_id: str
    suite_id: str
    min_quality_score: float
    min_calibration_score: float
    min_specialist_confidence: float
    max_age_seconds: int
    max_future_skew_seconds: int = 5

    def __post_init__(self) -> None:
        _identifier(self.owner_id, field="owner_id")
        _identifier(self.suite_id, field="suite_id")
        object.__setattr__(
            self, "min_quality_score", _score(self.min_quality_score, field="min_quality_score")
        )
        object.__setattr__(
            self,
            "min_calibration_score",
            _score(self.min_calibration_score, field="min_calibration_score"),
        )
        object.__setattr__(
            self,
            "min_specialist_confidence",
            _score(self.min_specialist_confidence, field="min_specialist_confidence"),
        )
        if isinstance(self.max_age_seconds, bool) or not isinstance(self.max_age_seconds, int):
            raise SpecializationError("max_age_seconds must be an integer")
        if self.max_age_seconds <= 0:
            raise SpecializationError("max_age_seconds must be positive")
        if (
            isinstance(self.max_future_skew_seconds, bool)
            or not isinstance(self.max_future_skew_seconds, int)
            or not 0 <= self.max_future_skew_seconds <= 300
        ):
            raise SpecializationError(
                "max_future_skew_seconds must be an integer between 0 and 300"
            )


@dataclass(frozen=True, slots=True)
class DomainProfile:
    domain_id: str
    description: str
    required_source_types: tuple[str, ...]
    required_tools: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    forbidden_assumptions: tuple[str, ...]
    evaluation: EvaluationOwnership

    def __post_init__(self) -> None:
        _identifier(self.domain_id, field="domain_id")
        object.__setattr__(self, "description", _bounded_text(self.description, field="description"))
        object.__setattr__(
            self,
            "required_source_types",
            _token_set(self.required_source_types, field="required_source_types"),
        )
        object.__setattr__(
            self, "required_tools", _token_set(self.required_tools, field="required_tools")
        )
        object.__setattr__(
            self, "allowed_tools", _token_set(self.allowed_tools, field="allowed_tools")
        )
        object.__setattr__(
            self,
            "forbidden_assumptions",
            _token_set(self.forbidden_assumptions, field="forbidden_assumptions"),
        )
        if not set(self.required_tools).issubset(self.allowed_tools):
            raise SpecializationError("required_tools must be a subset of allowed_tools")


@dataclass(frozen=True, slots=True)
class SpecialistCandidate:
    specialist_id: str
    domain_id: str
    source_types: tuple[str, ...]
    available_tools: tuple[str, ...]
    declared_assumptions: tuple[str, ...]
    confidence: float

    def __post_init__(self) -> None:
        _identifier(self.specialist_id, field="specialist_id")
        _identifier(self.domain_id, field="domain_id")
        object.__setattr__(self, "source_types", _token_set(self.source_types, field="source_types"))
        object.__setattr__(
            self, "available_tools", _token_set(self.available_tools, field="available_tools")
        )
        object.__setattr__(
            self,
            "declared_assumptions",
            _token_set(self.declared_assumptions, field="declared_assumptions"),
        )
        object.__setattr__(self, "confidence", _score(self.confidence, field="confidence"))


@dataclass(frozen=True, slots=True)
class SpecialistEvaluation:
    specialist_id: str
    domain_id: str
    owner_id: str
    suite_id: str
    evaluated_at: str
    quality_score: float
    calibration_score: float
    evidence_digest: str

    def __post_init__(self) -> None:
        _identifier(self.specialist_id, field="specialist_id")
        _identifier(self.domain_id, field="domain_id")
        _identifier(self.owner_id, field="owner_id")
        _identifier(self.suite_id, field="suite_id")
        _timestamp(self.evaluated_at, field="evaluated_at")
        object.__setattr__(
            self, "quality_score", _score(self.quality_score, field="quality_score")
        )
        object.__setattr__(
            self,
            "calibration_score",
            _score(self.calibration_score, field="calibration_score"),
        )
        if not isinstance(self.evidence_digest, str) or not _SHA256_RE.fullmatch(
            self.evidence_digest
        ):
            raise SpecializationError(
                "evidence_digest must be lowercase canonical sha256"
            )
        if self.owner_id == self.specialist_id:
            raise SpecializationError("specialists cannot self-own promotion evaluation")


@dataclass(frozen=True, slots=True)
class CandidateRejection:
    specialist_id: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.specialist_id, field="specialist_id")
        object.__setattr__(self, "reasons", _token_set(self.reasons, field="reasons"))
        if not self.reasons:
            raise SpecializationError("candidate rejection requires at least one reason")

    def to_wire(self) -> dict[str, object]:
        return {"specialist_id": self.specialist_id, "reasons": list(self.reasons)}


@dataclass(frozen=True, slots=True)
class SpecializedRoute:
    domain_id: str
    decision: RoutingDecision
    selected_specialist_id: str | None
    evaluated_at: str
    registry_digest: str
    rejection_details: tuple[CandidateRejection, ...]
    receipt_digest: str

    def to_wire(self) -> dict[str, object]:
        return {
            "domain_id": self.domain_id,
            "decision": self.decision.value,
            "selected_specialist_id": self.selected_specialist_id,
            "evaluated_at": self.evaluated_at,
            "registry_digest": self.registry_digest,
            "rejection_details": [item.to_wire() for item in self.rejection_details],
            "receipt_digest": self.receipt_digest,
        }


class DomainRegistry:
    """Canonical domain registry plus deterministic specialist eligibility gate."""

    def __init__(self, profiles: Iterable[DomainProfile]) -> None:
        items = tuple(profiles)
        if not items:
            raise SpecializationError("domain registry must contain at least one profile")
        if len(items) > _MAX_COLLECTION:
            raise SpecializationError("domain registry exceeds bounded cardinality")
        by_id: dict[str, DomainProfile] = {}
        for profile in items:
            if profile.domain_id in by_id:
                raise SpecializationError(f"duplicate domain profile {profile.domain_id}")
            by_id[profile.domain_id] = profile
        self._profiles = dict(sorted(by_id.items()))
        self._registry_digest = _digest_payload(
            {"profiles": [self._profile_wire(profile) for profile in self._profiles.values()]}
        )

    @property
    def registry_digest(self) -> str:
        return self._registry_digest

    @property
    def domain_ids(self) -> tuple[str, ...]:
        return tuple(self._profiles)

    def profile(self, domain_id: str) -> DomainProfile | None:
        return self._profiles.get(domain_id)

    @classmethod
    def from_manifest(cls, path: str | Path) -> "DomainRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            raise SpecializationError("domain registry schema_version must be 1")
        if payload.get("volume") != "VOL-071":
            raise SpecializationError("domain registry must bind VOL-071")
        raw_profiles = payload.get("profiles")
        if not isinstance(raw_profiles, list):
            raise SpecializationError("profiles must be a list")
        profiles: list[DomainProfile] = []
        for raw in raw_profiles:
            if not isinstance(raw, dict):
                raise SpecializationError("profile entries must be objects")
            raw_eval = raw.get("evaluation")
            if not isinstance(raw_eval, dict):
                raise SpecializationError("profile evaluation must be an object")
            evaluation = EvaluationOwnership(
                owner_id=raw_eval["owner_id"],
                suite_id=raw_eval["suite_id"],
                min_quality_score=raw_eval["min_quality_score"],
                min_calibration_score=raw_eval["min_calibration_score"],
                min_specialist_confidence=raw_eval["min_specialist_confidence"],
                max_age_seconds=raw_eval["max_age_seconds"],
                max_future_skew_seconds=raw_eval.get("max_future_skew_seconds", 5),
            )
            profiles.append(
                DomainProfile(
                    domain_id=raw["domain_id"],
                    description=raw["description"],
                    required_source_types=tuple(raw.get("required_source_types", ())),
                    required_tools=tuple(raw.get("required_tools", ())),
                    allowed_tools=tuple(raw.get("allowed_tools", ())),
                    forbidden_assumptions=tuple(raw.get("forbidden_assumptions", ())),
                    evaluation=evaluation,
                )
            )
        return cls(profiles)

    def route(
        self,
        domain_id: str,
        candidates: Iterable[SpecialistCandidate],
        evaluations: Iterable[SpecialistEvaluation],
        *,
        now: datetime,
    ) -> SpecializedRoute:
        _identifier(domain_id, field="domain_id")
        routed_at = _canonical_timestamp(now)
        profile = self._profiles.get(domain_id)
        if profile is None:
            return self._route(
                domain_id=domain_id,
                decision=RoutingDecision.GENERAL_FALLBACK,
                selected_specialist_id=None,
                evaluated_at=routed_at,
                rejections=(),
            )

        candidate_items = tuple(candidates)
        if len(candidate_items) > _MAX_COLLECTION:
            raise SpecializationError("candidate set exceeds bounded cardinality")
        candidate_ids = [item.specialist_id for item in candidate_items]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise SpecializationError("candidate set contains duplicate specialist identity")

        evaluation_items = tuple(evaluations)
        if len(evaluation_items) > _MAX_COLLECTION:
            raise SpecializationError("evaluation set exceeds bounded cardinality")
        evaluation_by_specialist: dict[str, SpecialistEvaluation] = {}
        for item in evaluation_items:
            if item.specialist_id in evaluation_by_specialist:
                raise SpecializationError(
                    f"duplicate evaluation identity for {item.specialist_id}"
                )
            evaluation_by_specialist[item.specialist_id] = item

        eligible: list[tuple[float, float, float, str]] = []
        rejections: list[CandidateRejection] = []
        for candidate in sorted(candidate_items, key=lambda item: item.specialist_id):
            reasons = self._candidate_reasons(
                profile,
                candidate,
                evaluation_by_specialist.get(candidate.specialist_id),
                now=now,
            )
            if reasons:
                rejections.append(
                    CandidateRejection(candidate.specialist_id, tuple(sorted(set(reasons))))
                )
                continue
            evaluation = evaluation_by_specialist[candidate.specialist_id]
            eligible.append(
                (
                    evaluation.quality_score,
                    evaluation.calibration_score,
                    candidate.confidence,
                    candidate.specialist_id,
                )
            )

        if not eligible:
            return self._route(
                domain_id=domain_id,
                decision=RoutingDecision.GENERAL_FALLBACK,
                selected_specialist_id=None,
                evaluated_at=routed_at,
                rejections=tuple(rejections),
            )

        eligible.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
        selected = eligible[0][3]
        return self._route(
            domain_id=domain_id,
            decision=RoutingDecision.SPECIALIST,
            selected_specialist_id=selected,
            evaluated_at=routed_at,
            rejections=tuple(rejections),
        )

    def verify(self, route: SpecializedRoute) -> None:
        if route.registry_digest != self.registry_digest:
            raise SpecializationError("route registry digest does not match active registry")
        expected = self._receipt_payload(
            domain_id=route.domain_id,
            decision=route.decision,
            selected_specialist_id=route.selected_specialist_id,
            evaluated_at=route.evaluated_at,
            rejections=route.rejection_details,
        )
        if _digest_payload(expected) != route.receipt_digest:
            raise SpecializationError("specialized route receipt failed integrity verification")
        if route.decision is RoutingDecision.SPECIALIST and not route.selected_specialist_id:
            raise SpecializationError("specialist route must identify a specialist")
        if route.decision is RoutingDecision.GENERAL_FALLBACK and route.selected_specialist_id:
            raise SpecializationError("general fallback cannot identify a specialist")

    def _candidate_reasons(
        self,
        profile: DomainProfile,
        candidate: SpecialistCandidate,
        evaluation: SpecialistEvaluation | None,
        *,
        now: datetime,
    ) -> list[str]:
        reasons: list[str] = []
        if candidate.domain_id != profile.domain_id:
            reasons.append("out-of-domain")
            return reasons
        if not set(profile.required_source_types).issubset(candidate.source_types):
            reasons.append("missing-required-sources")
        if not set(profile.required_tools).issubset(candidate.available_tools):
            reasons.append("missing-required-tools")
        if not set(candidate.available_tools).issubset(profile.allowed_tools):
            reasons.append("undeclared-tool-surface")
        if set(profile.forbidden_assumptions).intersection(candidate.declared_assumptions):
            reasons.append("forbidden-assumption")
        if candidate.confidence < profile.evaluation.min_specialist_confidence:
            reasons.append("insufficient-specialist-confidence")
        if evaluation is None:
            reasons.append("missing-evaluation")
            return reasons
        if evaluation.domain_id != profile.domain_id:
            reasons.append("evaluation-domain-mismatch")
        if evaluation.owner_id != profile.evaluation.owner_id:
            reasons.append("evaluation-owner-mismatch")
        if evaluation.suite_id != profile.evaluation.suite_id:
            reasons.append("evaluation-suite-mismatch")
        if evaluation.quality_score < profile.evaluation.min_quality_score:
            reasons.append("quality-below-threshold")
        if evaluation.calibration_score < profile.evaluation.min_calibration_score:
            reasons.append("calibration-below-threshold")

        evaluated = _timestamp(evaluation.evaluated_at, field="evaluated_at")
        now_utc = now.astimezone(timezone.utc)
        age = (now_utc - evaluated).total_seconds()
        if age < -profile.evaluation.max_future_skew_seconds:
            reasons.append("evaluation-from-future")
        elif age > profile.evaluation.max_age_seconds:
            reasons.append("stale-evaluation")
        return reasons

    def _route(
        self,
        *,
        domain_id: str,
        decision: RoutingDecision,
        selected_specialist_id: str | None,
        evaluated_at: str,
        rejections: tuple[CandidateRejection, ...],
    ) -> SpecializedRoute:
        canonical_rejections = tuple(
            sorted(rejections, key=lambda item: item.specialist_id)
        )
        payload = self._receipt_payload(
            domain_id=domain_id,
            decision=decision,
            selected_specialist_id=selected_specialist_id,
            evaluated_at=evaluated_at,
            rejections=canonical_rejections,
        )
        return SpecializedRoute(
            domain_id=domain_id,
            decision=decision,
            selected_specialist_id=selected_specialist_id,
            evaluated_at=evaluated_at,
            registry_digest=self.registry_digest,
            rejection_details=canonical_rejections,
            receipt_digest=_digest_payload(payload),
        )

    def _receipt_payload(
        self,
        *,
        domain_id: str,
        decision: RoutingDecision,
        selected_specialist_id: str | None,
        evaluated_at: str,
        rejections: tuple[CandidateRejection, ...],
    ) -> dict[str, object]:
        return {
            "domain_id": domain_id,
            "decision": decision.value,
            "selected_specialist_id": selected_specialist_id,
            "evaluated_at": evaluated_at,
            "registry_digest": self.registry_digest,
            "rejection_details": [item.to_wire() for item in rejections],
        }

    @staticmethod
    def _profile_wire(profile: DomainProfile) -> dict[str, object]:
        evaluation = profile.evaluation
        return {
            "domain_id": profile.domain_id,
            "description": profile.description,
            "required_source_types": list(profile.required_source_types),
            "required_tools": list(profile.required_tools),
            "allowed_tools": list(profile.allowed_tools),
            "forbidden_assumptions": list(profile.forbidden_assumptions),
            "evaluation": {
                "owner_id": evaluation.owner_id,
                "suite_id": evaluation.suite_id,
                "min_quality_score": evaluation.min_quality_score,
                "min_calibration_score": evaluation.min_calibration_score,
                "min_specialist_confidence": evaluation.min_specialist_confidence,
                "max_age_seconds": evaluation.max_age_seconds,
                "max_future_skew_seconds": evaluation.max_future_skew_seconds,
            },
        }


__all__ = [
    "CandidateRejection",
    "DomainProfile",
    "DomainRegistry",
    "EvaluationOwnership",
    "RoutingDecision",
    "SpecialistCandidate",
    "SpecialistEvaluation",
    "SpecializationError",
    "SpecializedRoute",
]
