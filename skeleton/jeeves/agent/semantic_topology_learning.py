"""Empirical lifecycle for proposed semantic-lens topology bridges.

The static semantic topology can identify unmodeled pairs of lenses whose cues
and roles suggest a potentially useful interaction.  Cue overlap alone is not
enough to turn that suggestion into an executable composition rule.

This module provides the missing lifecycle:

candidate -> predeclared trial -> calibration report -> active learned rule

A learned bridge remains an interpretive operator.  Promotion only authorizes
the semantic composition engine to test the interaction; it never creates
evidence, factual authority, or causal authority.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .epistemic_frontier import KnowledgeObligation
from .probability_lenses import (
    brier_score,
    expected_calibration_error,
    wilson_interval,
)
from .semantic_frontier import LensInteractionKind, LensInteractionRule
from .semantic_lens_topology import LensBridgeCandidate, SemanticLensTopology
from .semantic_lenses import LensFamily
from .types import (
    AgentContractError,
    bounded_text,
    json_safe,
    finite_number,
    positive_int,
    probability,
    stable_fingerprint,
    stable_id,
)


class TopologyBridgeStatus(str, Enum):
    SHADOW = "shadow"
    CANDIDATE = "candidate"
    ACTIVE = "active"
    RESTRICTED = "restricted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class TopologyBridgePrediction:
    prediction_id: str
    candidate_id: str
    candidate_fingerprint: str
    left_key: str
    right_key: str
    kind: LensInteractionKind
    predicted_probability: float
    domain: str
    independent_run: str
    predicted_at: float
    negative_control: bool = False
    source_finding_ids: tuple[str, ...] = ()
    source_forecast_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "prediction_id",
            "candidate_id",
            "candidate_fingerprint",
            "left_key",
            "right_key",
            "domain",
            "independent_run",
        ):
            value = str(getattr(self, name)).strip()
            if not value:
                raise AgentContractError(f"{name} is required")
            if name in {"left_key", "right_key", "domain"}:
                value = value.casefold()
            object.__setattr__(self, name, value)
        if self.left_key == self.right_key:
            raise AgentContractError(
                "topology bridge prediction requires distinct lenses"
            )
        if not isinstance(self.kind, LensInteractionKind):
            object.__setattr__(
                self,
                "kind",
                LensInteractionKind(str(self.kind)),
            )
        predicted_at = finite_number("predicted_at", self.predicted_at)
        if predicted_at < 0:
            raise AgentContractError(
                "topology bridge prediction time must be non-negative"
            )
        object.__setattr__(self, "predicted_at", predicted_at)
        object.__setattr__(
            self,
            "predicted_probability",
            probability(
                "predicted_probability",
                self.predicted_probability,
            ),
        )
        if not isinstance(self.negative_control, bool):
            raise AgentContractError("negative_control must be boolean")
        for name in (
            "source_finding_ids",
            "source_forecast_ids",
            "evidence_ids",
        ):
            object.__setattr__(
                self,
                name,
                tuple(
                    sorted(
                        {
                            str(value).strip()
                            for value in getattr(self, name)
                            if str(value).strip()
                        }
                    )
                ),
            )
        object.__setattr__(
            self,
            "metadata",
            json_safe(dict(self.metadata)),
        )

    def as_json(self) -> dict[str, Any]:
        payload = {
            "prediction_id": self.prediction_id,
            "candidate_id": self.candidate_id,
            "candidate_fingerprint": self.candidate_fingerprint,
            "left_key": self.left_key,
            "right_key": self.right_key,
            "kind": self.kind.value,
            "predicted_probability": self.predicted_probability,
            "domain": self.domain,
            "independent_run": self.independent_run,
            "predicted_at": self.predicted_at,
            "negative_control": self.negative_control,
            "source_finding_ids": list(self.source_finding_ids),
            "source_forecast_ids": list(self.source_forecast_ids),
            "evidence_ids": list(self.evidence_ids),
            "metadata": dict(self.metadata),
        }
        payload["fingerprint"] = self.fingerprint
        return json_safe(payload)

    @classmethod
    def from_json(
        cls,
        payload: Mapping[str, Any],
    ) -> "TopologyBridgePrediction":
        if not isinstance(payload, Mapping):
            raise TypeError("prediction payload must be a mapping")
        value = cls(
            prediction_id=str(payload.get("prediction_id", "")),
            candidate_id=str(payload.get("candidate_id", "")),
            candidate_fingerprint=str(
                payload.get("candidate_fingerprint", "")
            ),
            left_key=str(payload.get("left_key", "")),
            right_key=str(payload.get("right_key", "")),
            kind=LensInteractionKind(str(payload.get("kind", ""))),
            predicted_probability=payload.get(
                "predicted_probability",
                -1.0,
            ),
            domain=str(payload.get("domain", "")),
            independent_run=str(payload.get("independent_run", "")),
            predicted_at=payload.get("predicted_at", -1.0),
            negative_control=payload.get("negative_control", False),
            source_finding_ids=tuple(
                payload.get("source_finding_ids", ())
            ),
            source_forecast_ids=tuple(
                payload.get("source_forecast_ids", ())
            ),
            evidence_ids=tuple(payload.get("evidence_ids", ())),
            metadata=dict(payload.get("metadata", {})),
        )
        supplied = payload.get("fingerprint")
        if supplied is not None and str(supplied) != value.fingerprint:
            raise AgentContractError(
                "topology bridge prediction payload fingerprint mismatch"
            )
        return value

    @property
    def bridge_key(self) -> tuple[str, str]:
        return tuple(sorted((self.left_key, self.right_key)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "prediction": self.prediction_id,
                "candidate": self.candidate_id,
                "candidate_fingerprint": self.candidate_fingerprint,
                "bridge": self.bridge_key,
                "kind": self.kind.value,
                "probability": self.predicted_probability,
                "domain": self.domain,
                "run": self.independent_run,
                "predicted_at": self.predicted_at,
                "negative_control": self.negative_control,
                "findings": self.source_finding_ids,
                "forecasts": self.source_forecast_ids,
                "evidence": self.evidence_ids,
                "metadata": dict(self.metadata),
            }
        )


@dataclass(frozen=True, slots=True)
class TopologyBridgeTrial:
    trial_id: str
    prediction_id: str
    prediction_fingerprint: str
    candidate_id: str
    candidate_fingerprint: str
    left_key: str
    right_key: str
    kind: LensInteractionKind
    predicted_probability: float
    outcome: bool
    domain: str
    independent_run: str
    predicted_at: float
    observed_at: float
    negative_control: bool = False
    source_finding_ids: tuple[str, ...] = ()
    source_forecast_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    outcome_evidence_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "trial_id",
            "prediction_id",
            "prediction_fingerprint",
            "candidate_id",
            "candidate_fingerprint",
            "left_key",
            "right_key",
            "domain",
            "independent_run",
        ):
            value = str(getattr(self, name)).strip()
            if not value:
                raise AgentContractError(f"{name} is required")
            if name in {"left_key", "right_key", "domain"}:
                value = value.casefold()
            object.__setattr__(self, name, value)
        if self.left_key == self.right_key:
            raise AgentContractError(
                "topology bridge trial requires distinct lenses"
            )
        if not isinstance(self.kind, LensInteractionKind):
            object.__setattr__(
                self,
                "kind",
                LensInteractionKind(str(self.kind)),
            )
        predicted_at = finite_number("predicted_at", self.predicted_at)
        observed_at = finite_number("observed_at", self.observed_at)
        if predicted_at < 0 or observed_at < 0:
            raise AgentContractError(
                "topology bridge trial times must be non-negative"
            )
        if observed_at < predicted_at:
            raise AgentContractError(
                "topology bridge outcome cannot predate its prediction"
            )
        object.__setattr__(self, "predicted_at", predicted_at)
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(
            self,
            "predicted_probability",
            probability(
                "predicted_probability",
                self.predicted_probability,
            ),
        )
        if not isinstance(self.outcome, bool):
            raise AgentContractError(
                "topology bridge trial outcome must be boolean"
            )
        if not isinstance(self.negative_control, bool):
            raise AgentContractError("negative_control must be boolean")
        for name in (
            "source_finding_ids",
            "source_forecast_ids",
            "evidence_ids",
            "outcome_evidence_ids",
        ):
            object.__setattr__(
                self,
                name,
                tuple(
                    sorted(
                        {
                            str(value).strip()
                            for value in getattr(self, name)
                            if str(value).strip()
                        }
                    )
                ),
            )
        object.__setattr__(
            self,
            "metadata",
            json_safe(dict(self.metadata)),
        )

    def as_json(self) -> dict[str, Any]:
        payload = {
            "trial_id": self.trial_id,
            "prediction_id": self.prediction_id,
            "prediction_fingerprint": self.prediction_fingerprint,
            "candidate_id": self.candidate_id,
            "candidate_fingerprint": self.candidate_fingerprint,
            "left_key": self.left_key,
            "right_key": self.right_key,
            "kind": self.kind.value,
            "predicted_probability": self.predicted_probability,
            "outcome": self.outcome,
            "domain": self.domain,
            "independent_run": self.independent_run,
            "predicted_at": self.predicted_at,
            "observed_at": self.observed_at,
            "negative_control": self.negative_control,
            "source_finding_ids": list(self.source_finding_ids),
            "source_forecast_ids": list(self.source_forecast_ids),
            "evidence_ids": list(self.evidence_ids),
            "outcome_evidence_ids": list(self.outcome_evidence_ids),
            "metadata": dict(self.metadata),
        }
        payload["fingerprint"] = self.fingerprint
        return json_safe(payload)

    @classmethod
    def from_json(
        cls,
        payload: Mapping[str, Any],
    ) -> "TopologyBridgeTrial":
        if not isinstance(payload, Mapping):
            raise TypeError("trial payload must be a mapping")
        value = cls(
            trial_id=str(payload.get("trial_id", "")),
            prediction_id=str(payload.get("prediction_id", "")),
            prediction_fingerprint=str(
                payload.get("prediction_fingerprint", "")
            ),
            candidate_id=str(payload.get("candidate_id", "")),
            candidate_fingerprint=str(
                payload.get("candidate_fingerprint", "")
            ),
            left_key=str(payload.get("left_key", "")),
            right_key=str(payload.get("right_key", "")),
            kind=LensInteractionKind(str(payload.get("kind", ""))),
            predicted_probability=payload.get(
                "predicted_probability",
                -1.0,
            ),
            outcome=payload.get("outcome"),
            domain=str(payload.get("domain", "")),
            independent_run=str(payload.get("independent_run", "")),
            predicted_at=payload.get("predicted_at", -1.0),
            observed_at=payload.get("observed_at", -1.0),
            negative_control=payload.get("negative_control", False),
            source_finding_ids=tuple(
                payload.get("source_finding_ids", ())
            ),
            source_forecast_ids=tuple(
                payload.get("source_forecast_ids", ())
            ),
            evidence_ids=tuple(payload.get("evidence_ids", ())),
            outcome_evidence_ids=tuple(
                payload.get("outcome_evidence_ids", ())
            ),
            metadata=dict(payload.get("metadata", {})),
        )
        supplied = payload.get("fingerprint")
        if supplied is not None and str(supplied) != value.fingerprint:
            raise AgentContractError(
                "topology bridge trial payload fingerprint mismatch"
            )
        return value

    @classmethod
    def from_prediction(
        cls,
        prediction: TopologyBridgePrediction,
        *,
        trial_id: str,
        outcome: bool,
        observed_at: float,
        outcome_evidence_ids: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> "TopologyBridgeTrial":
        if not isinstance(prediction, TopologyBridgePrediction):
            raise TypeError(
                "prediction must be TopologyBridgePrediction"
            )
        return cls(
            trial_id=trial_id,
            prediction_id=prediction.prediction_id,
            prediction_fingerprint=prediction.fingerprint,
            candidate_id=prediction.candidate_id,
            candidate_fingerprint=prediction.candidate_fingerprint,
            left_key=prediction.left_key,
            right_key=prediction.right_key,
            kind=prediction.kind,
            predicted_probability=prediction.predicted_probability,
            outcome=outcome,
            domain=prediction.domain,
            independent_run=prediction.independent_run,
            predicted_at=prediction.predicted_at,
            observed_at=observed_at,
            negative_control=prediction.negative_control,
            source_finding_ids=prediction.source_finding_ids,
            source_forecast_ids=prediction.source_forecast_ids,
            evidence_ids=prediction.evidence_ids,
            outcome_evidence_ids=tuple(outcome_evidence_ids),
            metadata={
                "declared_before_outcome": True,
                **dict(prediction.metadata),
                **dict(metadata or {}),
            },
        )

    @property
    def bridge_key(self) -> tuple[str, str]:
        return tuple(sorted((self.left_key, self.right_key)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "trial": self.trial_id,
                "prediction": self.prediction_id,
                "prediction_fingerprint": self.prediction_fingerprint,
                "candidate": self.candidate_id,
                "candidate_fingerprint": self.candidate_fingerprint,
                "bridge": self.bridge_key,
                "kind": self.kind.value,
                "probability": self.predicted_probability,
                "outcome": self.outcome,
                "domain": self.domain,
                "run": self.independent_run,
                "predicted_at": self.predicted_at,
                "observed_at": self.observed_at,
                "negative_control": self.negative_control,
                "findings": self.source_finding_ids,
                "forecasts": self.source_forecast_ids,
                "evidence": self.evidence_ids,
                "outcome_evidence": self.outcome_evidence_ids,
                "metadata": dict(self.metadata),
            }
        )


@dataclass(frozen=True, slots=True)
class SemanticTopologyLearningState:
    """Versioned durable state for one topology-learning contract."""

    schema_version: int
    contract_fingerprint: str
    predictions: tuple[TopologyBridgePrediction, ...] = ()
    trials: tuple[TopologyBridgeTrial, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise AgentContractError(
                "unsupported semantic topology learning state version"
            )
        contract = str(self.contract_fingerprint).strip()
        if not contract:
            raise AgentContractError(
                "topology learning state contract fingerprint is required"
            )
        object.__setattr__(self, "contract_fingerprint", contract)

        predictions = tuple(
            sorted(
                tuple(self.predictions),
                key=lambda item: item.prediction_id,
            )
        )
        if any(
            not isinstance(item, TopologyBridgePrediction)
            for item in predictions
        ):
            raise AgentContractError(
                "topology learning state predictions are invalid"
            )
        prediction_ids = [item.prediction_id for item in predictions]
        if len(prediction_ids) != len(set(prediction_ids)):
            raise AgentContractError(
                "topology learning state has duplicate prediction ids"
            )

        trials = tuple(
            sorted(
                tuple(self.trials),
                key=lambda item: item.trial_id,
            )
        )
        if any(not isinstance(item, TopologyBridgeTrial) for item in trials):
            raise AgentContractError(
                "topology learning state trials are invalid"
            )
        trial_ids = [item.trial_id for item in trials]
        if len(trial_ids) != len(set(trial_ids)):
            raise AgentContractError(
                "topology learning state has duplicate trial ids"
            )
        object.__setattr__(self, "predictions", predictions)
        object.__setattr__(self, "trials", trials)

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "schema_version": self.schema_version,
                "contract": self.contract_fingerprint,
                "predictions": [
                    item.fingerprint for item in self.predictions
                ],
                "trials": [item.fingerprint for item in self.trials],
            }
        )

    def as_json(self) -> dict[str, Any]:
        return json_safe(
            {
                "schema_version": self.schema_version,
                "contract_fingerprint": self.contract_fingerprint,
                "predictions": [
                    item.as_json() for item in self.predictions
                ],
                "trials": [item.as_json() for item in self.trials],
                "fingerprint": self.fingerprint,
            }
        )

    @classmethod
    def from_json(
        cls,
        payload: Mapping[str, Any],
    ) -> "SemanticTopologyLearningState":
        if not isinstance(payload, Mapping):
            raise TypeError(
                "topology learning state payload must be a mapping"
            )
        raw_predictions = payload.get("predictions", ())
        raw_trials = payload.get("trials", ())
        if not isinstance(raw_predictions, (list, tuple)):
            raise AgentContractError(
                "topology learning predictions payload must be a sequence"
            )
        if not isinstance(raw_trials, (list, tuple)):
            raise AgentContractError(
                "topology learning trials payload must be a sequence"
            )
        state = cls(
            schema_version=int(payload.get("schema_version", 0)),
            contract_fingerprint=str(
                payload.get("contract_fingerprint", "")
            ),
            predictions=tuple(
                TopologyBridgePrediction.from_json(item)
                for item in raw_predictions
            ),
            trials=tuple(
                TopologyBridgeTrial.from_json(item)
                for item in raw_trials
            ),
        )
        supplied = payload.get("fingerprint")
        if supplied is not None and str(supplied) != state.fingerprint:
            raise AgentContractError(
                "topology learning state fingerprint mismatch"
            )
        return state


@dataclass(frozen=True, slots=True)
class TopologyBridgePolicy:
    minimum_trials: int = 8
    minimum_independent_runs: int = 4
    minimum_domains: int = 2
    minimum_negative_controls: int = 2
    maximum_brier: float = 0.24
    maximum_ece: float = 0.20
    minimum_empirical_rate: float = 0.55
    maximum_negative_control_positive_rate: float = 0.30
    reject_brier: float = 0.40
    reject_ece: float = 0.40
    reject_empirical_rate: float = 0.30

    def __post_init__(self) -> None:
        for name in (
            "minimum_trials",
            "minimum_independent_runs",
            "minimum_domains",
            "minimum_negative_controls",
        ):
            object.__setattr__(
                self,
                name,
                positive_int(name, getattr(self, name), maximum=1_000_000),
            )
        for name in (
            "maximum_brier",
            "maximum_ece",
            "minimum_empirical_rate",
            "maximum_negative_control_positive_rate",
            "reject_brier",
            "reject_ece",
            "reject_empirical_rate",
        ):
            object.__setattr__(
                self,
                name,
                probability(name, getattr(self, name)),
            )
        if self.reject_brier < self.maximum_brier:
            raise AgentContractError("reject_brier must be >= maximum_brier")
        if self.reject_ece < self.maximum_ece:
            raise AgentContractError("reject_ece must be >= maximum_ece")
        if self.reject_empirical_rate > self.minimum_empirical_rate:
            raise AgentContractError(
                "reject_empirical_rate must be <= minimum_empirical_rate"
            )

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "minimum_trials": self.minimum_trials,
                "minimum_independent_runs": self.minimum_independent_runs,
                "minimum_domains": self.minimum_domains,
                "minimum_negative_controls": self.minimum_negative_controls,
                "maximum_brier": self.maximum_brier,
                "maximum_ece": self.maximum_ece,
                "minimum_empirical_rate": self.minimum_empirical_rate,
                "maximum_negative_control_positive_rate": (
                    self.maximum_negative_control_positive_rate
                ),
                "reject_brier": self.reject_brier,
                "reject_ece": self.reject_ece,
                "reject_empirical_rate": self.reject_empirical_rate,
            }
        )


@dataclass(frozen=True, slots=True)
class TopologyBridgeReport:
    report_id: str
    candidate_id: str
    candidate_fingerprint: str
    left_key: str
    right_key: str
    kind: LensInteractionKind
    status: TopologyBridgeStatus
    trial_count: int
    independent_run_count: int
    domain_count: int
    negative_control_count: int
    mean_probability: float | None
    empirical_rate: float | None
    wilson_95: tuple[float, float] | None
    brier: float | None
    calibration_error: float | None
    negative_control_positive_rate: float | None
    reasons: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class LearnedTopologyRule:
    candidate_id: str
    candidate_fingerprint: str
    report_id: str
    report_fingerprint: str
    rule: LensInteractionRule
    fingerprint: str


@dataclass(frozen=True, slots=True)
class SemanticTopologyLearningSnapshot:
    prediction_count: int
    unresolved_prediction_count: int
    trial_count: int
    tested_bridge_count: int
    active_report_ids: tuple[str, ...]
    restricted_report_ids: tuple[str, ...]
    rejected_report_ids: tuple[str, ...]
    candidate_report_ids: tuple[str, ...]
    ambiguous_active_candidate_ids: tuple[str, ...]
    learned_rule_keys: tuple[tuple[str, str], ...]
    fingerprint: str


_FAMILY_AXIS_HINT: Mapping[LensFamily, str] = {
    LensFamily.FILM: "cinematic",
    LensFamily.LITERATURE: "literary",
    LensFamily.GAME: "ludic",
    LensFamily.NARRATIVE: "semantic",
    LensFamily.SEMIOTIC: "semantic",
    LensFamily.COGNITIVE: "memory",
    LensFamily.RHETORIC: "semantic",
    LensFamily.SOCIAL: "social",
    LensFamily.TEMPORAL: "temporal",
    LensFamily.SYSTEM: "system",
    LensFamily.CAUSAL: "causal",
    LensFamily.INFORMATION: "information",
    LensFamily.COMPUTATIONAL: "computational",
    LensFamily.METACOGNITIVE: "metacognitive",
    LensFamily.PROBABILITY: "probabilistic",
    LensFamily.PREDICTIVE: "predictive",
}


class SemanticTopologyLearningLab:
    """Validate topology bridge candidates before they can affect composition."""

    def __init__(
        self,
        topology: SemanticLensTopology,
        *,
        policy: TopologyBridgePolicy | None = None,
    ) -> None:
        if not isinstance(topology, SemanticLensTopology):
            raise TypeError("topology must be SemanticLensTopology")
        self.topology = topology
        self.policy = policy or TopologyBridgePolicy()
        candidates = topology.bridge_candidates(
            limit=10_000,
            minimum_score=0.0,
        )
        self._candidates = {item.candidate_id: item for item in candidates}
        self._predictions: dict[str, TopologyBridgePrediction] = {}
        self._trials: dict[str, TopologyBridgeTrial] = {}
        self._resolved_predictions: dict[str, str] = {}
        self._lock = threading.RLock()

    @staticmethod
    def candidate_fingerprint(candidate: LensBridgeCandidate) -> str:
        return stable_fingerprint(
            {
                "candidate": candidate.candidate_id,
                "left": candidate.left_key,
                "right": candidate.right_key,
                "left_family": candidate.left_family.value,
                "right_family": candidate.right_family.value,
                "score": candidate.score,
                "cue_overlap": candidate.cue_overlap,
                "role_novelty": candidate.role_novelty,
                "cross_family": candidate.cross_family,
                "shared_cues": candidate.shared_cues,
                "rationale": candidate.rationale,
            }
        )

    def candidate(self, candidate_id: str) -> LensBridgeCandidate | None:
        return self._candidates.get(str(candidate_id).strip())

    def _validate_prediction_candidate(
        self,
        prediction: TopologyBridgePrediction,
    ) -> LensBridgeCandidate:
        candidate = self._candidates.get(prediction.candidate_id)
        if candidate is None:
            raise AgentContractError(
                "unknown semantic topology bridge candidate"
            )
        expected_fingerprint = self.candidate_fingerprint(candidate)
        if prediction.candidate_fingerprint != expected_fingerprint:
            raise AgentContractError(
                "topology bridge candidate changed before prediction declaration"
            )
        if prediction.bridge_key != tuple(
            sorted((candidate.left_key, candidate.right_key))
        ):
            raise AgentContractError(
                "topology bridge prediction lens pair does not match candidate"
            )
        return candidate

    def declare(
        self,
        prediction: TopologyBridgePrediction,
    ) -> TopologyBridgePrediction:
        """Persist an immutable bridge prediction before its outcome exists."""

        if not isinstance(prediction, TopologyBridgePrediction):
            raise TypeError(
                "prediction must be TopologyBridgePrediction"
            )
        self._validate_prediction_candidate(prediction)
        with self._lock:
            existing = self._predictions.get(prediction.prediction_id)
            if existing is not None:
                if existing.fingerprint != prediction.fingerprint:
                    raise AgentContractError(
                        "topology bridge prediction id reused differently: "
                        + prediction.prediction_id
                    )
                return existing
            self._predictions[prediction.prediction_id] = prediction
        return prediction

    def prediction(
        self,
        prediction_id: str,
    ) -> TopologyBridgePrediction | None:
        with self._lock:
            return self._predictions.get(str(prediction_id).strip())

    @staticmethod
    def _trial_matches_prediction(
        trial: TopologyBridgeTrial,
        prediction: TopologyBridgePrediction,
    ) -> bool:
        return (
            trial.prediction_id == prediction.prediction_id
            and trial.prediction_fingerprint == prediction.fingerprint
            and trial.candidate_id == prediction.candidate_id
            and trial.candidate_fingerprint
            == prediction.candidate_fingerprint
            and trial.bridge_key == prediction.bridge_key
            and trial.kind is prediction.kind
            and trial.predicted_probability
            == prediction.predicted_probability
            and trial.domain == prediction.domain
            and trial.independent_run == prediction.independent_run
            and trial.predicted_at == prediction.predicted_at
            and trial.negative_control == prediction.negative_control
            and trial.source_finding_ids
            == prediction.source_finding_ids
            and trial.source_forecast_ids
            == prediction.source_forecast_ids
            and trial.evidence_ids == prediction.evidence_ids
        )

    def record(self, trial: TopologyBridgeTrial) -> TopologyBridgeTrial:
        """Record a resolved trial only when its prediction was predeclared."""

        if not isinstance(trial, TopologyBridgeTrial):
            raise TypeError("trial must be TopologyBridgeTrial")
        candidate = self._candidates.get(trial.candidate_id)
        if candidate is None:
            raise AgentContractError(
                "unknown semantic topology bridge candidate"
            )
        expected_fingerprint = self.candidate_fingerprint(candidate)
        if trial.candidate_fingerprint != expected_fingerprint:
            raise AgentContractError(
                "topology bridge candidate changed after trial declaration"
            )
        if trial.bridge_key != tuple(
            sorted((candidate.left_key, candidate.right_key))
        ):
            raise AgentContractError(
                "topology bridge trial lens pair does not match candidate"
            )

        with self._lock:
            prediction = self._predictions.get(trial.prediction_id)
            if prediction is None:
                raise AgentContractError(
                    "topology bridge prediction must be declared before outcome"
                )
            if not self._trial_matches_prediction(trial, prediction):
                raise AgentContractError(
                    "topology bridge trial differs from declared prediction"
                )

            existing = self._trials.get(trial.trial_id)
            if existing is not None:
                if existing.fingerprint != trial.fingerprint:
                    raise AgentContractError(
                        "topology bridge trial id reused differently: "
                        + trial.trial_id
                    )
                return existing

            prior_trial_id = self._resolved_predictions.get(
                trial.prediction_id
            )
            if prior_trial_id is not None:
                prior = self._trials[prior_trial_id]
                if prior.fingerprint == trial.fingerprint:
                    return prior
                raise AgentContractError(
                    "topology bridge prediction already resolved differently"
                )

            self._trials[trial.trial_id] = trial
            self._resolved_predictions[trial.prediction_id] = trial.trial_id
        return trial

    def resolve(
        self,
        prediction_id: str,
        *,
        outcome: bool,
        observed_at: float,
        outcome_evidence_ids: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> TopologyBridgeTrial:
        """Resolve a previously declared prediction exactly once."""

        with self._lock:
            prediction = self._predictions.get(str(prediction_id).strip())
            if prediction is None:
                raise AgentContractError(
                    "unknown topology bridge prediction"
                )
            trial_id = stable_id(
                "semantic-topology-trial",
                {
                    "prediction": prediction.prediction_id,
                    "prediction_fingerprint": prediction.fingerprint,
                },
                length=32,
            )
            trial = TopologyBridgeTrial.from_prediction(
                prediction,
                trial_id=trial_id,
                outcome=outcome,
                observed_at=observed_at,
                outcome_evidence_ids=outcome_evidence_ids,
                metadata=metadata,
            )
            return self.record(trial)

    def trials(
        self,
        candidate_id: str,
        *,
        kind: LensInteractionKind | None = None,
    ) -> tuple[TopologyBridgeTrial, ...]:
        candidate_key = str(candidate_id).strip()
        kind_value = (
            kind
            if kind is None or isinstance(kind, LensInteractionKind)
            else LensInteractionKind(str(kind))
        )
        with self._lock:
            values = [
                trial
                for trial in self._trials.values()
                if trial.candidate_id == candidate_key
                and (kind_value is None or trial.kind is kind_value)
            ]
        return tuple(sorted(values, key=lambda item: item.trial_id))

    def _report_status(
        self,
        *,
        trial_count: int,
        independent_runs: int,
        domains: int,
        negative_control_count: int,
        brier: float,
        calibration_error: float,
        empirical_rate: float,
        negative_control_positive_rate: float | None,
    ) -> tuple[TopologyBridgeStatus, tuple[str, ...]]:
        reasons: list[str] = []
        if trial_count < self.policy.minimum_trials:
            reasons.append("insufficient_trials")
        if independent_runs < self.policy.minimum_independent_runs:
            reasons.append("insufficient_independent_runs")
        if domains < self.policy.minimum_domains:
            reasons.append("insufficient_domain_replication")
        if negative_control_count < self.policy.minimum_negative_controls:
            reasons.append("insufficient_negative_controls")

        enough_for_rejection = trial_count >= self.policy.minimum_trials
        if enough_for_rejection and brier >= self.policy.reject_brier:
            reasons.append("brier_rejection_threshold")
        if enough_for_rejection and calibration_error >= self.policy.reject_ece:
            reasons.append("calibration_rejection_threshold")
        if (
            enough_for_rejection
            and empirical_rate <= self.policy.reject_empirical_rate
        ):
            reasons.append("empirical_rate_rejection_threshold")
        rejection = any(reason.endswith("rejection_threshold") for reason in reasons)
        if rejection:
            return TopologyBridgeStatus.REJECTED, tuple(reasons)

        negative_control_failed = (
            negative_control_positive_rate is not None
            and negative_control_count >= self.policy.minimum_negative_controls
            and negative_control_positive_rate
            > self.policy.maximum_negative_control_positive_rate
        )
        if negative_control_failed:
            reasons.append("negative_control_failure")

        complete = (
            trial_count >= self.policy.minimum_trials
            and independent_runs >= self.policy.minimum_independent_runs
            and domains >= self.policy.minimum_domains
            and negative_control_count >= self.policy.minimum_negative_controls
        )
        calibrated = (
            brier <= self.policy.maximum_brier
            and calibration_error <= self.policy.maximum_ece
            and empirical_rate >= self.policy.minimum_empirical_rate
            and not negative_control_failed
        )
        if complete and calibrated:
            reasons.append("replicated_calibrated_bridge")
            return TopologyBridgeStatus.ACTIVE, tuple(reasons)
        if complete:
            reasons.append("replication_complete_but_promotion_thresholds_unmet")
            return TopologyBridgeStatus.RESTRICTED, tuple(reasons)
        return TopologyBridgeStatus.CANDIDATE, tuple(reasons)

    def report(
        self,
        candidate_id: str,
        kind: LensInteractionKind,
    ) -> TopologyBridgeReport:
        candidate = self._candidates.get(str(candidate_id).strip())
        if candidate is None:
            raise AgentContractError("unknown semantic topology bridge candidate")
        kind_value = (
            kind
            if isinstance(kind, LensInteractionKind)
            else LensInteractionKind(str(kind))
        )
        rows = self.trials(candidate.candidate_id, kind=kind_value)
        candidate_fingerprint = self.candidate_fingerprint(candidate)
        report_id = stable_id(
            "semantic-topology-report",
            {
                "candidate": candidate_fingerprint,
                "kind": kind_value.value,
            },
            length=28,
        )
        if not rows:
            fingerprint = stable_fingerprint(
                {
                    "report": report_id,
                    "candidate": candidate_fingerprint,
                    "kind": kind_value.value,
                    "status": TopologyBridgeStatus.SHADOW.value,
                    "policy": self.policy.fingerprint,
                }
            )
            return TopologyBridgeReport(
                report_id=report_id,
                candidate_id=candidate.candidate_id,
                candidate_fingerprint=candidate_fingerprint,
                left_key=candidate.left_key,
                right_key=candidate.right_key,
                kind=kind_value,
                status=TopologyBridgeStatus.SHADOW,
                trial_count=0,
                independent_run_count=0,
                domain_count=0,
                negative_control_count=0,
                mean_probability=None,
                empirical_rate=None,
                wilson_95=None,
                brier=None,
                calibration_error=None,
                negative_control_positive_rate=None,
                reasons=("no_trials",),
                fingerprint=fingerprint,
            )

        primary = [item for item in rows if not item.negative_control]
        controls = [item for item in rows if item.negative_control]
        if not primary:
            fingerprint = stable_fingerprint(
                {
                    "report": report_id,
                    "candidate": candidate_fingerprint,
                    "kind": kind_value.value,
                    "trials": [item.fingerprint for item in rows],
                    "status": TopologyBridgeStatus.CANDIDATE.value,
                    "reasons": ("no_primary_trials",),
                    "policy": self.policy.fingerprint,
                }
            )
            return TopologyBridgeReport(
                report_id=report_id,
                candidate_id=candidate.candidate_id,
                candidate_fingerprint=candidate_fingerprint,
                left_key=candidate.left_key,
                right_key=candidate.right_key,
                kind=kind_value,
                status=TopologyBridgeStatus.CANDIDATE,
                trial_count=0,
                independent_run_count=0,
                domain_count=0,
                negative_control_count=len(controls),
                mean_probability=None,
                empirical_rate=None,
                wilson_95=None,
                brier=None,
                calibration_error=None,
                negative_control_positive_rate=(
                    None
                    if not controls
                    else sum(item.outcome for item in controls) / len(controls)
                ),
                reasons=("no_primary_trials",),
                fingerprint=fingerprint,
            )

        probabilities = [item.predicted_probability for item in primary]
        outcomes = [item.outcome for item in primary]
        positive_count = sum(outcomes)
        mean_probability = sum(probabilities) / len(probabilities)
        empirical_rate = positive_count / len(primary)
        interval = wilson_interval(positive_count, len(primary))
        brier = brier_score(probabilities, outcomes)
        calibration_error = expected_calibration_error(
            probabilities,
            outcomes,
            bins=min(10, len(primary)),
        )
        runs = {item.independent_run for item in primary}
        domains = {item.domain for item in primary}
        control_rate = (
            None
            if not controls
            else sum(item.outcome for item in controls) / len(controls)
        )
        status, reasons = self._report_status(
            trial_count=len(primary),
            independent_runs=len(runs),
            domains=len(domains),
            negative_control_count=len(controls),
            brier=brier,
            calibration_error=calibration_error,
            empirical_rate=empirical_rate,
            negative_control_positive_rate=control_rate,
        )
        fingerprint = stable_fingerprint(
            {
                "report": report_id,
                "candidate": candidate_fingerprint,
                "kind": kind_value.value,
                "trials": [item.fingerprint for item in rows],
                "status": status.value,
                "metrics": {
                    "mean_probability": mean_probability,
                    "empirical_rate": empirical_rate,
                    "wilson_95": interval,
                    "brier": brier,
                    "calibration_error": calibration_error,
                    "negative_control_positive_rate": control_rate,
                },
                "reasons": reasons,
                "policy": self.policy.fingerprint,
            }
        )
        return TopologyBridgeReport(
            report_id=report_id,
            candidate_id=candidate.candidate_id,
            candidate_fingerprint=candidate_fingerprint,
            left_key=candidate.left_key,
            right_key=candidate.right_key,
            kind=kind_value,
            status=status,
            trial_count=len(primary),
            independent_run_count=len(runs),
            domain_count=len(domains),
            negative_control_count=len(controls),
            mean_probability=mean_probability,
            empirical_rate=empirical_rate,
            wilson_95=interval,
            brier=brier,
            calibration_error=calibration_error,
            negative_control_positive_rate=control_rate,
            reasons=reasons,
            fingerprint=fingerprint,
        )

    def reports(self) -> tuple[TopologyBridgeReport, ...]:
        with self._lock:
            identities = sorted(
                {
                    (trial.candidate_id, trial.kind)
                    for trial in self._trials.values()
                },
                key=lambda item: (item[0], item[1].value),
            )
        return tuple(self.report(candidate_id, kind) for candidate_id, kind in identities)

    def _learned_rules_from_reports(
        self,
        reports: Sequence[TopologyBridgeReport],
    ) -> tuple[LearnedTopologyRule, ...]:
        learned: list[LearnedTopologyRule] = []
        active_by_candidate: dict[str, list[TopologyBridgeReport]] = {}
        for report in reports:
            if report.status is TopologyBridgeStatus.ACTIVE:
                active_by_candidate.setdefault(report.candidate_id, []).append(
                    report
                )
        for candidate_id, active_reports in sorted(active_by_candidate.items()):
            # Competing relation kinds for the same pair are a model-selection
            # problem, not permission to execute multiple contradictory rules.
            if len(active_reports) != 1:
                continue
            report = active_reports[0]
            candidate = self._candidates[candidate_id]
            axis_hint = _FAMILY_AXIS_HINT.get(
                candidate.right_family
                if candidate.cross_family
                else candidate.left_family,
                "semantic",
            )
            rule = LensInteractionRule(
                left_key=candidate.left_key,
                right_key=candidate.right_key,
                kind=report.kind,
                rationale=(
                    "Replicated learned semantic-topology bridge. "
                    f"Validated across {report.trial_count} scored trials, "
                    f"{report.independent_run_count} independent runs, and "
                    f"{report.domain_count} domains. The relation remains "
                    "interpretive and cannot create evidence."
                ),
                question=(
                    f"Does joint use of {candidate.left_key} and "
                    f"{candidate.right_key} reproduce the registered "
                    f"{report.kind.value} relation on a new independent case?"
                ),
                predictive_effect=(
                    "Use the bridge only as a falsifiable semantic interaction; "
                    "retest under domain shift and preserve counter-readings."
                ),
                symmetric=True,
                tangent_axis_hint=axis_hint,
                metadata={
                    "rule_source": "learned_topology",
                    "candidate_id": candidate.candidate_id,
                    "candidate_fingerprint": report.candidate_fingerprint,
                    "report_id": report.report_id,
                    "report_fingerprint": report.fingerprint,
                    "evidence_ceiling": "interpretive_only",
                    "may_promote_to_evidence": False,
                },
            )
            fingerprint = stable_fingerprint(
                {
                    "candidate": report.candidate_fingerprint,
                    "report": report.fingerprint,
                    "rule": {
                        "key": rule.key,
                        "kind": rule.kind.value,
                        "rationale": rule.rationale,
                        "question": rule.question,
                        "predictive_effect": rule.predictive_effect,
                        "axis": rule.tangent_axis_hint,
                        "metadata": dict(rule.metadata),
                    },
                }
            )
            learned.append(
                LearnedTopologyRule(
                    candidate_id=report.candidate_id,
                    candidate_fingerprint=report.candidate_fingerprint,
                    report_id=report.report_id,
                    report_fingerprint=report.fingerprint,
                    rule=rule,
                    fingerprint=fingerprint,
                )
            )
        learned.sort(
            key=lambda item: (
                item.rule.key,
                item.rule.kind.value,
                item.candidate_id,
            )
        )
        return tuple(learned)

    def _snapshot_from_reports(
        self,
        reports: Sequence[TopologyBridgeReport],
        learned: Sequence[LearnedTopologyRule],
    ) -> SemanticTopologyLearningSnapshot:
        active = tuple(
            item.report_id
            for item in reports
            if item.status is TopologyBridgeStatus.ACTIVE
        )
        restricted = tuple(
            item.report_id
            for item in reports
            if item.status is TopologyBridgeStatus.RESTRICTED
        )
        rejected = tuple(
            item.report_id
            for item in reports
            if item.status is TopologyBridgeStatus.REJECTED
        )
        candidates = tuple(
            item.report_id
            for item in reports
            if item.status is TopologyBridgeStatus.CANDIDATE
        )
        active_by_candidate: dict[str, int] = {}
        for item in reports:
            if item.status is TopologyBridgeStatus.ACTIVE:
                active_by_candidate[item.candidate_id] = (
                    active_by_candidate.get(item.candidate_id, 0) + 1
                )
        ambiguous = tuple(
            sorted(
                candidate_id
                for candidate_id, count in active_by_candidate.items()
                if count > 1
            )
        )
        trial_count = len(self._trials)
        prediction_count = len(self._predictions)
        unresolved_prediction_count = (
            prediction_count - len(self._resolved_predictions)
        )
        fingerprint = stable_fingerprint(
            {
                "topology": self.topology.fingerprint,
                "policy": self.policy.fingerprint,
                "reports": [item.fingerprint for item in reports],
                "learned": [item.fingerprint for item in learned],
                "ambiguous_active_candidates": ambiguous,
                "prediction_count": prediction_count,
                "unresolved_prediction_count": unresolved_prediction_count,
                "trial_count": trial_count,
            }
        )
        return SemanticTopologyLearningSnapshot(
            prediction_count=prediction_count,
            unresolved_prediction_count=unresolved_prediction_count,
            trial_count=trial_count,
            tested_bridge_count=len({item.candidate_id for item in reports}),
            active_report_ids=active,
            restricted_report_ids=restricted,
            rejected_report_ids=rejected,
            candidate_report_ids=candidates,
            ambiguous_active_candidate_ids=ambiguous,
            learned_rule_keys=tuple(item.rule.key for item in learned),
            fingerprint=fingerprint,
        )

    def research_obligations(
        self,
        *,
        limit: int = 24,
        minimum_candidate_score: float = 0.18,
        include_rejected: bool = False,
    ) -> tuple[KnowledgeObligation, ...]:
        """Convert unresolved topology gaps into epistemic-frontier obligations.

        This does not promote a topology bridge. It only gives the research
        control plane a typed, rankable question about what would need to be
        learned before the bridge could become executable.
        """

        maximum = positive_int("limit", limit, maximum=10_000)
        threshold = probability(
            "minimum_candidate_score",
            minimum_candidate_score,
        )
        if not isinstance(include_rejected, bool):
            raise AgentContractError("include_rejected must be boolean")

        with self._lock:
            reports = self.reports()
            learned = self._learned_rules_from_reports(reports)
            learned_candidate_ids = {
                item.candidate_id for item in learned
            }
            reports_by_candidate: dict[
                str,
                list[TopologyBridgeReport],
            ] = {}
            for report in reports:
                reports_by_candidate.setdefault(
                    report.candidate_id,
                    [],
                ).append(report)

            obligations: list[tuple[float, KnowledgeObligation]] = []
            for candidate in self._candidates.values():
                if candidate.score < threshold:
                    continue
                if candidate.candidate_id in learned_candidate_ids:
                    continue

                candidate_reports = reports_by_candidate.get(
                    candidate.candidate_id,
                    [],
                )
                active_reports = [
                    item
                    for item in candidate_reports
                    if item.status is TopologyBridgeStatus.ACTIVE
                ]
                ambiguous = len(active_reports) > 1
                rejected_only = (
                    bool(candidate_reports)
                    and all(
                        item.status is TopologyBridgeStatus.REJECTED
                        for item in candidate_reports
                    )
                )
                if rejected_only and not include_rejected:
                    continue

                candidate_trials = [
                    item
                    for item in self._trials.values()
                    if item.candidate_id == candidate.candidate_id
                ]
                primary = [
                    item
                    for item in candidate_trials
                    if not item.negative_control
                ]
                controls = [
                    item
                    for item in candidate_trials
                    if item.negative_control
                ]
                run_count = len(
                    {item.independent_run for item in primary}
                )
                domain_count = len({item.domain for item in primary})
                trial_coverage = min(
                    1.0,
                    len(primary) / self.policy.minimum_trials,
                )
                run_coverage = min(
                    1.0,
                    run_count / self.policy.minimum_independent_runs,
                )
                domain_coverage = min(
                    1.0,
                    domain_count / self.policy.minimum_domains,
                )
                control_coverage = min(
                    1.0,
                    len(controls) / self.policy.minimum_negative_controls,
                )
                evidence_coverage = min(
                    1.0,
                    0.45 * trial_coverage
                    + 0.20 * run_coverage
                    + 0.20 * domain_coverage
                    + 0.15 * control_coverage,
                )

                best_report = None
                if candidate_reports:
                    status_order = {
                        TopologyBridgeStatus.ACTIVE: 4,
                        TopologyBridgeStatus.RESTRICTED: 3,
                        TopologyBridgeStatus.CANDIDATE: 2,
                        TopologyBridgeStatus.REJECTED: 1,
                        TopologyBridgeStatus.SHADOW: 0,
                    }
                    best_report = max(
                        candidate_reports,
                        key=lambda item: (
                            status_order[item.status],
                            item.trial_count,
                            item.domain_count,
                            item.independent_run_count,
                            -(
                                item.brier
                                if item.brier is not None
                                else 1.0
                            ),
                        ),
                    )

                empirical_rate = (
                    best_report.empirical_rate
                    if best_report is not None
                    and best_report.empirical_rate is not None
                    else 0.5
                )
                confidence = min(
                    1.0,
                    max(
                        0.0,
                        0.5
                        + (empirical_rate - 0.5)
                        * evidence_coverage,
                    ),
                )
                if ambiguous:
                    confidence = 0.5

                unresolved_status = (
                    "ambiguous_active"
                    if ambiguous
                    else (
                        best_report.status.value
                        if best_report is not None
                        else TopologyBridgeStatus.SHADOW.value
                    )
                )
                kind_text = (
                    best_report.kind.value
                    if best_report is not None and not ambiguous
                    else "interaction"
                )
                question = (
                    (
                        "Which interaction kind is reproducibly supported "
                        f"between {candidate.left_key} and "
                        f"{candidate.right_key}, given competing active "
                        "bridge hypotheses?"
                    )
                    if ambiguous
                    else (
                        f"Does a reproducible {kind_text} relation exist "
                        f"between {candidate.left_key} and "
                        f"{candidate.right_key} across independent runs "
                        "and domains?"
                    )
                )
                decision_impact = min(
                    1.0,
                    0.55 * candidate.score
                    + 0.20 * float(candidate.cross_family)
                    + 0.15 * candidate.role_novelty
                    + 0.10 * candidate.cue_overlap,
                )
                contradiction_strength = (
                    1.0
                    if ambiguous
                    else (
                        0.65
                        if best_report is not None
                        and best_report.status
                        in {
                            TopologyBridgeStatus.RESTRICTED,
                            TopologyBridgeStatus.REJECTED,
                        }
                        else 0.0
                    )
                )
                model_disagreement = (
                    1.0
                    if ambiguous
                    else min(
                        1.0,
                        max(0, len(candidate_reports) - 1) / 3.0,
                    )
                )
                obligation = KnowledgeObligation(
                    obligation_id=stable_id(
                        "semantic-topology-obligation",
                        {
                            "candidate": candidate.candidate_id,
                        },
                        length=28,
                    ),
                    question=question,
                    decision_impact=decision_impact,
                    confidence=confidence,
                    evidence_coverage=evidence_coverage,
                    freshness=1.0,
                    contradiction_strength=contradiction_strength,
                    model_disagreement=model_disagreement,
                    assumption_load=0.85,
                    novelty=max(
                        candidate.role_novelty,
                        0.75 if candidate.cross_family else 0.45,
                    ),
                    assumptions=(
                        "shared cues do not establish an interaction",
                        "semantic topology relations remain interpretive",
                        "promotion requires predeclared independent outcomes",
                    ),
                    metadata={
                        "semantic_topology": True,
                        "candidate_id": candidate.candidate_id,
                        "candidate_fingerprint": (
                            self.candidate_fingerprint(candidate)
                        ),
                        "left_key": candidate.left_key,
                        "right_key": candidate.right_key,
                        "left_family": candidate.left_family.value,
                        "right_family": candidate.right_family.value,
                        "candidate_score": candidate.score,
                        "cross_family": candidate.cross_family,
                        "shared_cues": list(candidate.shared_cues),
                        "status": unresolved_status,
                        "report_ids": [
                            item.report_id
                            for item in candidate_reports
                        ],
                        "active_kinds": [
                            item.kind.value for item in active_reports
                        ],
                        "primary_trial_count": len(primary),
                        "negative_control_count": len(controls),
                        "independent_run_count": run_count,
                        "domain_count": domain_count,
                        "topology_learning_contract": (
                            self.contract_fingerprint
                        ),
                    },
                )
                obligations.append(
                    (
                        decision_impact
                        * (1.0 - 0.5 * evidence_coverage)
                        + 0.25 * contradiction_strength
                        + 0.20 * model_disagreement,
                        obligation,
                    )
                )

        obligations.sort(
            key=lambda item: (
                -item[0],
                item[1].obligation_id,
            )
        )
        return tuple(
            item[1] for item in obligations[:maximum]
        )

    def export_state(self) -> SemanticTopologyLearningState:
        """Export a versioned immutable snapshot for durable storage."""

        with self._lock:
            return SemanticTopologyLearningState(
                schema_version=1,
                contract_fingerprint=self.contract_fingerprint,
                predictions=tuple(self._predictions.values()),
                trials=tuple(self._trials.values()),
            )

    def restore_state(
        self,
        state: SemanticTopologyLearningState | Mapping[str, Any],
    ) -> SemanticTopologyLearningSnapshot:
        """Atomically replace learning state after full contract validation."""

        restored = (
            state
            if isinstance(state, SemanticTopologyLearningState)
            else SemanticTopologyLearningState.from_json(state)
        )
        if restored.contract_fingerprint != self.contract_fingerprint:
            raise AgentContractError(
                "topology learning state contract fingerprint mismatch"
            )

        staged_predictions: dict[str, TopologyBridgePrediction] = {}
        for prediction in restored.predictions:
            self._validate_prediction_candidate(prediction)
            if prediction.prediction_id in staged_predictions:
                raise AgentContractError(
                    "duplicate topology bridge prediction during restore"
                )
            staged_predictions[prediction.prediction_id] = prediction

        staged_trials: dict[str, TopologyBridgeTrial] = {}
        staged_resolved: dict[str, str] = {}
        for trial in restored.trials:
            candidate = self._candidates.get(trial.candidate_id)
            if candidate is None:
                raise AgentContractError(
                    "restored trial references unknown topology candidate"
                )
            expected_candidate = self.candidate_fingerprint(candidate)
            if trial.candidate_fingerprint != expected_candidate:
                raise AgentContractError(
                    "restored topology candidate fingerprint mismatch"
                )
            prediction = staged_predictions.get(trial.prediction_id)
            if prediction is None:
                raise AgentContractError(
                    "restored topology trial has no declared prediction"
                )
            if not self._trial_matches_prediction(trial, prediction):
                raise AgentContractError(
                    "restored topology trial differs from prediction custody"
                )
            if trial.trial_id in staged_trials:
                raise AgentContractError(
                    "duplicate topology bridge trial during restore"
                )
            prior_trial = staged_resolved.get(trial.prediction_id)
            if prior_trial is not None:
                raise AgentContractError(
                    "restored topology prediction has multiple outcomes"
                )
            staged_trials[trial.trial_id] = trial
            staged_resolved[trial.prediction_id] = trial.trial_id

        with self._lock:
            self._predictions = staged_predictions
            self._trials = staged_trials
            self._resolved_predictions = staged_resolved
            reports = self.reports()
            learned = self._learned_rules_from_reports(reports)
            snapshot = self._snapshot_from_reports(reports, learned)
        return snapshot

    def evaluate(
        self,
    ) -> tuple[
        tuple[LearnedTopologyRule, ...],
        SemanticTopologyLearningSnapshot,
    ]:
        """Read learned rules and diagnostics from one atomic trial revision."""

        with self._lock:
            reports = self.reports()
            learned = self._learned_rules_from_reports(reports)
            snapshot = self._snapshot_from_reports(reports, learned)
        return learned, snapshot

    def learned_rules(self) -> tuple[LearnedTopologyRule, ...]:
        return self.evaluate()[0]

    def snapshot(self) -> SemanticTopologyLearningSnapshot:
        return self.evaluate()[1]

    @property
    def contract_fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "topology": self.topology.fingerprint,
                "policy": self.policy.fingerprint,
                "candidate_count": len(self._candidates),
            }
        )

    @property
    def fingerprint(self) -> str:
        with self._lock:
            predictions = [
                (prediction_id, prediction.fingerprint)
                for prediction_id, prediction
                in sorted(self._predictions.items())
            ]
            trials = [
                (trial_id, trial.fingerprint)
                for trial_id, trial in sorted(self._trials.items())
            ]
        return stable_fingerprint(
            {
                "contract": self.contract_fingerprint,
                "predictions": predictions,
                "trials": trials,
            }
        )


__all__ = [
    "LearnedTopologyRule",
    "SemanticTopologyLearningLab",
    "SemanticTopologyLearningSnapshot",
    "SemanticTopologyLearningState",
    "TopologyBridgePolicy",
    "TopologyBridgePrediction",
    "TopologyBridgeReport",
    "TopologyBridgeStatus",
    "TopologyBridgeTrial",
]
