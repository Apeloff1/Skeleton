"""Deterministic worker/job affinity matching and load-aware placement."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

from skeleton.shells.worker_heartbeat import LivenessView, WorkerLiveness
from skeleton.shells.worker_identity import WorkerIdentity, WorkerRegistration, WorkerRole


class AffinityMode(str, Enum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    AVOID = "avoid"


@dataclass(frozen=True)
class AffinityTerm:
    key: str
    value: str
    mode: AffinityMode = AffinityMode.REQUIRED
    weight: int = 1

    def __post_init__(self) -> None:
        if not self.key or len(self.key) > 64:
            raise ValueError("invalid affinity key")
        if not self.value or len(self.value) > 128:
            raise ValueError("invalid affinity value")
        if not isinstance(self.mode, AffinityMode):
            object.__setattr__(self, "mode", AffinityMode(self.mode))
        if isinstance(self.weight, bool) or not isinstance(self.weight, int) or self.weight <= 0 or self.weight > 1000:
            raise ValueError("affinity weight outside supported bounds")


@dataclass(frozen=True)
class JobRequirements:
    required_role: WorkerRole | None = None
    required_features: frozenset[str] = frozenset()
    affinity: tuple[AffinityTerm, ...] = ()
    max_inflight: int | None = None
    allow_late_workers: bool = False

    def __post_init__(self) -> None:
        if self.required_role is not None and not isinstance(self.required_role, WorkerRole):
            object.__setattr__(self, "required_role", WorkerRole(self.required_role))
        object.__setattr__(self, "required_features", frozenset(self.required_features))
        object.__setattr__(self, "affinity", tuple(self.affinity))
        if self.max_inflight is not None:
            if isinstance(self.max_inflight, bool) or not isinstance(self.max_inflight, int) or self.max_inflight < 0:
                raise ValueError("max_inflight must be a non-negative integer")


@dataclass(frozen=True)
class WorkerCandidate:
    registration: WorkerRegistration
    liveness: LivenessView
    rank_value: int
    preferred_matches: int
    avoided_matches: int
    reasons: tuple[str, ...] = ()

    @property
    def worker_id(self) -> str:
        return self.registration.identity.worker_id

    def to_dict(self) -> dict[str, object]:
        return {
            "worker_id": self.worker_id,
            "generation": self.registration.identity.generation,
            "rank_value": self.rank_value,
            "preferred_matches": self.preferred_matches,
            "avoided_matches": self.avoided_matches,
            "liveness": self.liveness.liveness.value,
            "inflight": self.liveness.inflight,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class PlacementDecision:
    selected: WorkerCandidate | None
    candidates: tuple[WorkerCandidate, ...]
    rejected: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "rejected", MappingProxyType(dict(self.rejected)))

    @property
    def placed(self) -> bool:
        return self.selected is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "placed": self.placed,
            "selected": None if self.selected is None else self.selected.to_dict(),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "rejected": {key: list(value) for key, value in self.rejected.items()},
        }


def _term_matches(identity: WorkerIdentity, term: AffinityTerm) -> bool:
    if term.key == "role":
        return identity.role.value == term.value
    if term.key == "feature":
        return term.value in identity.features
    return identity.labels.get(term.key) == term.value


class WorkerPlacement:
    """Pure deterministic worker placement based on identity and liveness."""

    def evaluate(
        self,
        registrations: Sequence[WorkerRegistration],
        liveness: Mapping[str, LivenessView],
        requirements: JobRequirements | None = None,
    ) -> PlacementDecision:
        requirements = requirements or JobRequirements()
        candidates: list[WorkerCandidate] = []
        rejected: dict[str, tuple[str, ...]] = {}

        for registration in registrations:
            identity = registration.identity
            reasons: list[str] = []
            view = liveness.get(
                identity.worker_id,
                LivenessView(
                    identity.worker_id,
                    identity.generation,
                    WorkerLiveness.UNKNOWN,
                    None,
                    None,
                    False,
                    0,
                ),
            )

            if not registration.enabled:
                reasons.append("registration disabled")
            if requirements.required_role is not None and identity.role is not requirements.required_role:
                reasons.append("role mismatch")
            missing = requirements.required_features - identity.features
            if missing:
                reasons.append("missing required feature")
            if view.liveness in {WorkerLiveness.STALE, WorkerLiveness.UNKNOWN}:
                reasons.append("worker is not live")
            if view.liveness is WorkerLiveness.LATE and not requirements.allow_late_workers:
                reasons.append("worker heartbeat is late")
            if requirements.max_inflight is not None and view.inflight >= requirements.max_inflight:
                reasons.append("worker inflight limit reached")

            preferred = 0
            avoided = 0
            required_failed = False
            rank_value = 0
            for term in requirements.affinity:
                matches = _term_matches(identity, term)
                if term.mode is AffinityMode.REQUIRED and not matches:
                    required_failed = True
                elif term.mode is AffinityMode.PREFERRED and matches:
                    preferred += 1
                    rank_value += term.weight
                elif term.mode is AffinityMode.AVOID and matches:
                    avoided += 1
                    rank_value -= term.weight
            if required_failed:
                reasons.append("required affinity mismatch")

            if reasons:
                rejected[identity.worker_id] = tuple(reasons)
                continue

            # Lower inflight is preferred after explicit affinity. Healthy gets
            # a deterministic bonus over late workers when late is permitted.
            rank_value -= view.inflight
            if view.liveness is WorkerLiveness.HEALTHY:
                rank_value += 10

            candidates.append(
                WorkerCandidate(
                    registration=registration,
                    liveness=view,
                    rank_value=rank_value,
                    preferred_matches=preferred,
                    avoided_matches=avoided,
                )
            )

        candidates.sort(
            key=lambda item: (
                -item.rank_value,
                item.liveness.inflight,
                item.registration.identity.key,
            )
        )
        return PlacementDecision(
            selected=candidates[0] if candidates else None,
            candidates=tuple(candidates),
            rejected=rejected,
        )

    def select(
        self,
        registrations: Sequence[WorkerRegistration],
        liveness: Mapping[str, LivenessView],
        requirements: JobRequirements | None = None,
    ) -> WorkerRegistration | None:
        decision = self.evaluate(registrations, liveness, requirements)
        return None if decision.selected is None else decision.selected.registration
