"""Canonical evidence-gated technology radar for VOL-114.

The radar is an architecture decision support contract, not an adoption shortcut.
Candidates start as intent, experiments stay isolated from adopted architecture,
and promotion requires exact evidence plus an independently represented
architecture decision bound to the same candidate revision and evidence set.

The state machine is intentionally fail-closed:
candidate -> experiment -> adopted -> retired
candidate/experiment may also be retired as abandoned work. An adopted
technology cannot disappear without explicit retirement evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import re
from itertools import islice
from typing import Iterable, Mapping

RADAR_SCHEMA = "skeleton.contracts.technology_radar.v1"
_MAX_CANDIDATES = 10_000
_MAX_EVIDENCE = 50_000
_MAX_TEXT = 4_096
_MAX_TICK = 2_147_483_647
_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RadarError(ValueError):
    """Technology-radar state is malformed, contradictory, or unsafe."""


class RadarState(str, Enum):
    CANDIDATE = "candidate"
    EXPERIMENT = "experiment"
    ADOPTED = "adopted"
    RETIRED = "retired"


class EvidenceKind(str, Enum):
    FUNCTIONAL = "functional"
    COST = "cost"
    RISK = "risk"
    INTEGRATION = "integration"
    SECURITY = "security"
    RETIREMENT = "retirement"


def _id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise RadarError(f"{field} must be stable identifier")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise RadarError(f"{field} must be lowercase sha256")
    return value


def _text(value: object, field: str, *, maximum: int = _MAX_TEXT) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        raise RadarError(f"{field} must be bounded canonical text")
    if any(ord(char) < 32 and char not in "\t" for char in value):
        raise RadarError(f"{field} contains control characters")
    return value


def _nonnegative_int(value: object, field: str, maximum: int = _MAX_TICK) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RadarError(f"{field} must be integer")
    if not 0 <= value <= maximum:
        raise RadarError(f"{field} must be within [0, {maximum}]")
    return value


def _positive_int(value: object, field: str, maximum: int = _MAX_TICK) -> int:
    value = _nonnegative_int(value, field, maximum)
    if value < 1:
        raise RadarError(f"{field} must be positive")
    return value


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RadarError("radar state must be deterministic JSON") from exc
    return sha256(raw).hexdigest()


def technology_evidence_set_digest(
    items: Iterable["TechnologyEvidence"],
) -> str:
    """Return deterministic identity for an exact technology evidence set."""

    try:
        materialized = tuple(islice(iter(items), _MAX_EVIDENCE + 1))
    except TypeError as exc:
        raise TypeError("items must be iterable") from exc
    if len(materialized) > _MAX_EVIDENCE:
        raise RadarError("evidence set exceeds safety bound")
    if any(not isinstance(item, TechnologyEvidence) for item in materialized):
        raise TypeError("items must contain TechnologyEvidence")
    evidence_ids = [item.evidence_id for item in materialized]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise RadarError("duplicate technology evidence id in evidence set")
    return _digest(sorted(item.digest for item in materialized))


def _evidence_set_digest(items: Iterable["TechnologyEvidence"]) -> str:
    return technology_evidence_set_digest(items)


@dataclass(frozen=True, slots=True)
class TechnologyExitCriteria:
    max_cost: int
    max_risk: int
    decision_tick: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_cost",
            _nonnegative_int(self.max_cost, "max_cost"),
        )
        object.__setattr__(
            self,
            "max_risk",
            _nonnegative_int(self.max_risk, "max_risk"),
        )
        object.__setattr__(
            self,
            "decision_tick",
            _positive_int(self.decision_tick, "decision_tick"),
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                RADAR_SCHEMA,
                self.max_cost,
                self.max_risk,
                self.decision_tick,
            ]
        )


@dataclass(frozen=True, slots=True)
class TechnologyCandidate:
    technology_id: str
    purpose: str
    baseline_id: str
    owner_id: str
    budget: int
    decision_tick: int
    exit: TechnologyExitCriteria

    def __post_init__(self) -> None:
        for field in ("technology_id", "baseline_id", "owner_id"):
            object.__setattr__(
                self,
                field,
                _id(getattr(self, field), field),
            )
        object.__setattr__(self, "purpose", _text(self.purpose, "purpose"))
        object.__setattr__(self, "budget", _positive_int(self.budget, "budget"))
        object.__setattr__(
            self,
            "decision_tick",
            _positive_int(self.decision_tick, "decision_tick"),
        )
        if not isinstance(self.exit, TechnologyExitCriteria):
            raise RadarError("exit must be TechnologyExitCriteria")
        if self.exit.decision_tick != self.decision_tick:
            raise RadarError(
                "candidate and exit decision horizons must match"
            )
        if self.budget > self.exit.max_cost:
            raise RadarError(
                "candidate budget exceeds exit cost criterion"
            )

    @property
    def digest(self) -> str:
        return _digest(
            [
                RADAR_SCHEMA,
                self.technology_id,
                self.purpose,
                self.baseline_id,
                self.owner_id,
                self.budget,
                self.decision_tick,
                self.exit.digest,
            ]
        )


@dataclass(frozen=True, slots=True)
class TechnologyEvidence:
    evidence_id: str
    technology_id: str
    candidate_digest: str
    kind: EvidenceKind
    observed_tick: int
    passed: bool
    artifact_digest: str
    metric_value: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _id(self.evidence_id, "evidence_id"))
        object.__setattr__(
            self,
            "technology_id",
            _id(self.technology_id, "technology_id"),
        )
        object.__setattr__(
            self,
            "candidate_digest",
            _sha(self.candidate_digest, "candidate_digest"),
        )
        if not isinstance(self.kind, EvidenceKind):
            raise RadarError("kind must be EvidenceKind")
        object.__setattr__(
            self,
            "observed_tick",
            _nonnegative_int(self.observed_tick, "observed_tick"),
        )
        if not isinstance(self.passed, bool):
            raise RadarError("passed must be boolean")
        object.__setattr__(
            self,
            "artifact_digest",
            _sha(self.artifact_digest, "artifact_digest"),
        )
        if self.metric_value is not None:
            object.__setattr__(
                self,
                "metric_value",
                _nonnegative_int(self.metric_value, "metric_value"),
            )
        if self.kind in (EvidenceKind.COST, EvidenceKind.RISK):
            if self.metric_value is None:
                raise RadarError("cost/risk evidence requires metric_value")
        elif self.metric_value is not None:
            raise RadarError("metric_value is only valid for cost/risk evidence")

    @property
    def digest(self) -> str:
        return _digest(
            [
                RADAR_SCHEMA,
                self.evidence_id,
                self.technology_id,
                self.candidate_digest,
                self.kind.value,
                self.observed_tick,
                self.passed,
                self.artifact_digest,
                self.metric_value,
            ]
        )


@dataclass(frozen=True, slots=True)
class ArchitectureDecision:
    decision_id: str
    technology_id: str
    candidate_digest: str
    evidence_set_digest: str
    owner_id: str
    observed_tick: int
    approved: bool

    def __post_init__(self) -> None:
        for field in ("decision_id", "technology_id", "owner_id"):
            object.__setattr__(
                self,
                field,
                _id(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "candidate_digest",
            _sha(self.candidate_digest, "candidate_digest"),
        )
        object.__setattr__(
            self,
            "evidence_set_digest",
            _sha(self.evidence_set_digest, "evidence_set_digest"),
        )
        object.__setattr__(
            self,
            "observed_tick",
            _nonnegative_int(self.observed_tick, "observed_tick"),
        )
        if not isinstance(self.approved, bool):
            raise RadarError("approved must be boolean")

    @property
    def digest(self) -> str:
        return _digest(
            [
                RADAR_SCHEMA,
                self.decision_id,
                self.technology_id,
                self.candidate_digest,
                self.evidence_set_digest,
                self.owner_id,
                self.observed_tick,
                self.approved,
            ]
        )


@dataclass(frozen=True, slots=True)
class RadarDecision:
    technology_id: str
    state: RadarState
    evidence_ids: tuple[str, ...]
    architecture_decision_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "technology_id",
            _id(self.technology_id, "technology_id"),
        )
        if not isinstance(self.state, RadarState):
            raise RadarError("state must be RadarState")
        if not isinstance(self.evidence_ids, tuple):
            raise RadarError("evidence_ids must be tuple")
        evidence_ids = tuple(
            _id(item, "evidence_id") for item in self.evidence_ids
        )
        if len(evidence_ids) != len(set(evidence_ids)):
            raise RadarError("duplicate evidence id in decision")
        object.__setattr__(self, "evidence_ids", tuple(sorted(evidence_ids)))
        if self.architecture_decision_id is not None:
            object.__setattr__(
                self,
                "architecture_decision_id",
                _id(
                    self.architecture_decision_id,
                    "architecture_decision_id",
                ),
            )
        if self.state is RadarState.ADOPTED:
            if not self.evidence_ids or self.architecture_decision_id is None:
                raise RadarError(
                    "adoption requires evidence and architecture decision"
                )
        elif self.architecture_decision_id is not None:
            raise RadarError(
                "architecture decision is only valid for adoption"
            )

    @property
    def digest(self) -> str:
        return _digest(
            [
                RADAR_SCHEMA,
                self.technology_id,
                self.state.value,
                list(self.evidence_ids),
                self.architecture_decision_id,
            ]
        )


@dataclass(frozen=True, slots=True)
class RadarTransition:
    sequence: int
    technology_id: str
    from_state: RadarState
    to_state: RadarState
    current_tick: int
    decision_digest: str
    evidence_set_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _positive_int(self.sequence, "sequence"))
        object.__setattr__(
            self,
            "technology_id",
            _id(self.technology_id, "technology_id"),
        )
        if not isinstance(self.from_state, RadarState):
            raise RadarError("from_state must be RadarState")
        if not isinstance(self.to_state, RadarState):
            raise RadarError("to_state must be RadarState")
        object.__setattr__(
            self,
            "current_tick",
            _nonnegative_int(self.current_tick, "current_tick"),
        )
        object.__setattr__(
            self,
            "decision_digest",
            _sha(self.decision_digest, "decision_digest"),
        )
        object.__setattr__(
            self,
            "evidence_set_digest",
            _sha(self.evidence_set_digest, "evidence_set_digest"),
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                RADAR_SCHEMA,
                self.sequence,
                self.technology_id,
                self.from_state.value,
                self.to_state.value,
                self.current_tick,
                self.decision_digest,
                self.evidence_set_digest,
            ]
        )


@dataclass(frozen=True, slots=True)
class RadarSnapshot:
    registry_digest: str
    states: tuple[tuple[str, RadarState], ...]
    transition_digests: tuple[str, ...]

    @property
    def digest(self) -> str:
        return _digest(
            [
                RADAR_SCHEMA,
                self.registry_digest,
                [(item, state.value) for item, state in self.states],
                list(self.transition_digests),
            ]
        )


class TechnologyRadar:
    """Evidence-gated technology lifecycle with deterministic transition history."""

    _ALLOWED = {
        RadarState.CANDIDATE: {RadarState.EXPERIMENT, RadarState.RETIRED},
        RadarState.EXPERIMENT: {RadarState.ADOPTED, RadarState.RETIRED},
        RadarState.ADOPTED: {RadarState.RETIRED},
        RadarState.RETIRED: set(),
    }

    def __init__(
        self,
        candidates: Iterable[TechnologyCandidate],
        evidence: Iterable[TechnologyEvidence] = (),
        architecture_decisions: Iterable[ArchitectureDecision] = (),
    ) -> None:
        try:
            materialized_candidates = tuple(
                islice(iter(candidates), _MAX_CANDIDATES + 1)
            )
        except TypeError as exc:
            raise TypeError("candidates must be iterable") from exc
        try:
            materialized_evidence = tuple(
                islice(iter(evidence), _MAX_EVIDENCE + 1)
            )
        except TypeError as exc:
            raise TypeError("evidence must be iterable") from exc
        try:
            materialized_adrs = tuple(
                islice(iter(architecture_decisions), _MAX_CANDIDATES + 1)
            )
        except TypeError as exc:
            raise TypeError("architecture_decisions must be iterable") from exc

        if len(materialized_candidates) > _MAX_CANDIDATES:
            raise RadarError("candidate count exceeds safety bound")
        if len(materialized_evidence) > _MAX_EVIDENCE:
            raise RadarError("evidence count exceeds safety bound")
        if len(materialized_adrs) > _MAX_CANDIDATES:
            raise RadarError("architecture decision count exceeds safety bound")
        if any(
            not isinstance(item, TechnologyCandidate)
            for item in materialized_candidates
        ):
            raise TypeError("candidates must contain TechnologyCandidate")
        if any(
            not isinstance(item, TechnologyEvidence)
            for item in materialized_evidence
        ):
            raise TypeError("evidence must contain TechnologyEvidence")
        if any(
            not isinstance(item, ArchitectureDecision)
            for item in materialized_adrs
        ):
            raise TypeError(
                "architecture_decisions must contain ArchitectureDecision"
            )

        candidate_ids = [item.technology_id for item in materialized_candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise RadarError("duplicate technology candidate")

        evidence_ids = [item.evidence_id for item in materialized_evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise RadarError("duplicate technology evidence id")

        adr_ids = [item.decision_id for item in materialized_adrs]
        if len(adr_ids) != len(set(adr_ids)):
            raise RadarError("duplicate architecture decision id")

        self.candidates = {
            item.technology_id: item
            for item in sorted(
                materialized_candidates,
                key=lambda item: item.technology_id,
            )
        }
        self.evidence = {
            item.evidence_id: item
            for item in sorted(
                materialized_evidence,
                key=lambda item: item.evidence_id,
            )
        }
        self.architecture_decisions = {
            item.decision_id: item
            for item in sorted(
                materialized_adrs,
                key=lambda item: item.decision_id,
            )
        }

        for item in self.evidence.values():
            self._validate_evidence_binding(item)
        for item in self.architecture_decisions.values():
            self._validate_adr_subject(item)

        self.states = {
            technology_id: RadarState.CANDIDATE
            for technology_id in self.candidates
        }
        self._transitions: list[RadarTransition] = []

    def _candidate(self, technology_id: str) -> TechnologyCandidate:
        technology_id = _id(technology_id, "technology_id")
        try:
            return self.candidates[technology_id]
        except KeyError as exc:
            raise RadarError("unknown technology") from exc

    def _validate_evidence_binding(self, item: TechnologyEvidence) -> None:
        candidate = self._candidate(item.technology_id)
        if item.candidate_digest != candidate.digest:
            raise RadarError("evidence candidate digest mismatch")

    def _validate_adr_subject(self, item: ArchitectureDecision) -> None:
        candidate = self._candidate(item.technology_id)
        if item.candidate_digest != candidate.digest:
            raise RadarError("architecture decision candidate digest mismatch")
        if item.owner_id != candidate.owner_id:
            raise RadarError("architecture decision owner mismatch")

    def _evidence_for_decision(
        self,
        decision: RadarDecision,
        *,
        current_tick: int,
    ) -> tuple[TechnologyEvidence, ...]:
        selected: list[TechnologyEvidence] = []
        for evidence_id in decision.evidence_ids:
            try:
                item = self.evidence[evidence_id]
            except KeyError as exc:
                raise RadarError("decision references unknown evidence") from exc
            if item.technology_id != decision.technology_id:
                raise RadarError("decision references foreign technology evidence")
            if item.observed_tick > current_tick:
                raise RadarError("decision references future evidence")
            if not item.passed:
                raise RadarError("decision references failed evidence")
            selected.append(item)
        return tuple(selected)

    def _validate_adoption(
        self,
        candidate: TechnologyCandidate,
        decision: RadarDecision,
        selected: tuple[TechnologyEvidence, ...],
        *,
        current_tick: int,
    ) -> None:
        kinds = {item.kind for item in selected}
        required = {
            EvidenceKind.FUNCTIONAL,
            EvidenceKind.COST,
            EvidenceKind.RISK,
        }
        missing = sorted(item.value for item in required - kinds)
        if missing:
            raise RadarError(
                "adoption missing required evidence kinds: " + ",".join(missing)
            )

        costs = [
            item.metric_value
            for item in selected
            if item.kind is EvidenceKind.COST
        ]
        risks = [
            item.metric_value
            for item in selected
            if item.kind is EvidenceKind.RISK
        ]
        assert all(item is not None for item in costs + risks)

        observed_cost = max(int(item) for item in costs)
        observed_risk = max(int(item) for item in risks)

        if observed_cost > candidate.exit.max_cost:
            raise RadarError("experiment exceeds exit cost threshold")
        if observed_cost > candidate.budget:
            raise RadarError("experiment exceeds candidate budget")
        if observed_risk > candidate.exit.max_risk:
            raise RadarError("experiment exceeds exit risk threshold")

        adr_id = decision.architecture_decision_id
        assert adr_id is not None
        try:
            adr = self.architecture_decisions[adr_id]
        except KeyError as exc:
            raise RadarError("adoption references unknown architecture decision") from exc

        if adr.technology_id != candidate.technology_id:
            raise RadarError("architecture decision technology mismatch")
        if adr.candidate_digest != candidate.digest:
            raise RadarError("architecture decision candidate mismatch")
        if adr.observed_tick > current_tick:
            raise RadarError("architecture decision is from the future")
        if not adr.approved:
            raise RadarError("architecture decision rejected adoption")

        evidence_digest = _evidence_set_digest(selected)
        if adr.evidence_set_digest != evidence_digest:
            raise RadarError("architecture decision evidence set mismatch")

    def _validate_retirement(
        self,
        prior: RadarState,
        selected: tuple[TechnologyEvidence, ...],
    ) -> None:
        retirement = [
            item for item in selected if item.kind is EvidenceKind.RETIREMENT
        ]
        if not retirement:
            raise RadarError(
                "retirement requires explicit retirement evidence"
            )

    @property
    def registry_digest(self) -> str:
        return _digest(
            [
                RADAR_SCHEMA,
                [item.digest for item in self.candidates.values()],
                [item.digest for item in self.evidence.values()],
                [
                    item.digest
                    for item in self.architecture_decisions.values()
                ],
            ]
        )

    @property
    def transitions(self) -> tuple[RadarTransition, ...]:
        return tuple(self._transitions)

    def state(self, technology_id: str) -> RadarState:
        candidate = self._candidate(technology_id)
        return self.states[candidate.technology_id]

    def decide(self, decision: RadarDecision, current_tick: int) -> RadarState:
        if not isinstance(decision, RadarDecision):
            raise TypeError("decision must be RadarDecision")
        current_tick = _nonnegative_int(current_tick, "current_tick")
        candidate = self._candidate(decision.technology_id)

        prior = self.states[candidate.technology_id]
        if decision.state not in self._ALLOWED[prior]:
            raise RadarError("invalid radar transition")

        if (
            decision.state is not RadarState.RETIRED
            and (
                current_tick > candidate.decision_tick
                or current_tick > candidate.exit.decision_tick
            )
        ):
            raise RadarError("decision horizon expired")

        selected = self._evidence_for_decision(
            decision,
            current_tick=current_tick,
        )

        if decision.state is RadarState.ADOPTED:
            self._validate_adoption(
                candidate,
                decision,
                selected,
                current_tick=current_tick,
            )
        elif decision.state is RadarState.RETIRED:
            self._validate_retirement(prior, selected)

        evidence_digest = _evidence_set_digest(selected)
        transition = RadarTransition(
            sequence=len(self._transitions) + 1,
            technology_id=candidate.technology_id,
            from_state=prior,
            to_state=decision.state,
            current_tick=current_tick,
            decision_digest=decision.digest,
            evidence_set_digest=evidence_digest,
        )

        self.states[candidate.technology_id] = decision.state
        self._transitions.append(transition)
        return decision.state

    def snapshot(self) -> RadarSnapshot:
        return RadarSnapshot(
            registry_digest=self.registry_digest,
            states=tuple(sorted(self.states.items())),
            transition_digests=tuple(
                item.digest for item in self._transitions
            ),
        )


__all__ = [
    "RADAR_SCHEMA",
    "ArchitectureDecision",
    "EvidenceKind",
    "RadarDecision",
    "RadarError",
    "RadarSnapshot",
    "RadarState",
    "RadarTransition",
    "TechnologyCandidate",
    "TechnologyEvidence",
    "TechnologyExitCriteria",
    "TechnologyRadar",
    "technology_evidence_set_digest",
]
