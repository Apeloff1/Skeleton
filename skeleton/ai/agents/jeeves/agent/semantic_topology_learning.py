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
    def slot_key(self) -> tuple[str, str, str, str, bool]:
        return (
            self.candidate_id,
            self.kind.value,
            self.domain,
            self.independent_run,
            self.negative_control,
        )

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
    minimum_trials_per_domain: int = 2
    minimum_independent_runs_per_domain: int = 2
    minimum_negative_controls: int = 2
    minimum_control_domains: int = 2
    minimum_controls_per_domain: int = 1
    minimum_control_runs_per_domain: int = 1
    maximum_predictions: int = 500_000
    maximum_trials: int = 500_000
    maximum_unresolved_predictions: int = 50_000
    maximum_brier: float = 0.24
    maximum_ece: float = 0.20
    minimum_empirical_rate: float = 0.55
    maximum_negative_control_positive_rate: float = 0.30
    maximum_domain_brier: float = 0.32
    minimum_domain_empirical_rate: float = 0.45
    maximum_domain_control_positive_rate: float = 0.50
    reject_brier: float = 0.40
    reject_ece: float = 0.40
    reject_empirical_rate: float = 0.30
    reject_domain_brier: float = 0.60
    reject_domain_empirical_rate: float = 0.20

    def __post_init__(self) -> None:
        for name in (
            "minimum_trials",
            "minimum_independent_runs",
            "minimum_domains",
            "minimum_trials_per_domain",
            "minimum_independent_runs_per_domain",
            "minimum_negative_controls",
            "minimum_control_domains",
            "minimum_controls_per_domain",
            "minimum_control_runs_per_domain",
            "maximum_predictions",
            "maximum_trials",
            "maximum_unresolved_predictions",
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
            "maximum_domain_brier",
            "minimum_domain_empirical_rate",
            "maximum_domain_control_positive_rate",
            "reject_brier",
            "reject_ece",
            "reject_empirical_rate",
            "reject_domain_brier",
            "reject_domain_empirical_rate",
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
        if self.reject_domain_brier < self.maximum_domain_brier:
            raise AgentContractError(
                "reject_domain_brier must be >= maximum_domain_brier"
            )
        if (
            self.reject_domain_empirical_rate
            > self.minimum_domain_empirical_rate
        ):
            raise AgentContractError(
                "reject_domain_empirical_rate must be <= "
                "minimum_domain_empirical_rate"
            )
        if (
            self.maximum_unresolved_predictions
            > self.maximum_predictions
        ):
            raise AgentContractError(
                "maximum_unresolved_predictions cannot exceed "
                "maximum_predictions"
            )

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "minimum_trials": self.minimum_trials,
                "minimum_independent_runs": self.minimum_independent_runs,
                "minimum_domains": self.minimum_domains,
                "minimum_trials_per_domain": self.minimum_trials_per_domain,
                "minimum_independent_runs_per_domain": (
                    self.minimum_independent_runs_per_domain
                ),
                "minimum_negative_controls": self.minimum_negative_controls,
                "minimum_control_domains": self.minimum_control_domains,
                "minimum_controls_per_domain": (
                    self.minimum_controls_per_domain
                ),
                "minimum_control_runs_per_domain": (
                    self.minimum_control_runs_per_domain
                ),
                "maximum_predictions": self.maximum_predictions,
                "maximum_trials": self.maximum_trials,
                "maximum_unresolved_predictions": (
                    self.maximum_unresolved_predictions
                ),
                "maximum_brier": self.maximum_brier,
                "maximum_ece": self.maximum_ece,
                "minimum_empirical_rate": self.minimum_empirical_rate,
                "maximum_negative_control_positive_rate": (
                    self.maximum_negative_control_positive_rate
                ),
                "maximum_domain_brier": self.maximum_domain_brier,
                "minimum_domain_empirical_rate": (
                    self.minimum_domain_empirical_rate
                ),
                "maximum_domain_control_positive_rate": (
                    self.maximum_domain_control_positive_rate
                ),
                "reject_brier": self.reject_brier,
                "reject_ece": self.reject_ece,
                "reject_empirical_rate": self.reject_empirical_rate,
                "reject_domain_brier": self.reject_domain_brier,
                "reject_domain_empirical_rate": (
                    self.reject_domain_empirical_rate
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class TopologyBridgeDomainReport:
    domain: str
    trial_count: int
    independent_run_count: int
    negative_control_count: int
    negative_control_run_count: int
    mean_probability: float | None
    empirical_rate: float | None
    wilson_95: tuple[float, float] | None
    brier: float | None
    calibration_error: float | None
    negative_control_positive_rate: float | None
    qualified_primary: bool
    qualified_control: bool
    fingerprint: str

    def as_json(self) -> dict[str, Any]:
        return json_safe(
            {
                "domain": self.domain,
                "trial_count": self.trial_count,
                "independent_run_count": self.independent_run_count,
                "negative_control_count": self.negative_control_count,
                "negative_control_run_count": (
                    self.negative_control_run_count
                ),
                "mean_probability": self.mean_probability,
                "empirical_rate": self.empirical_rate,
                "wilson_95": self.wilson_95,
                "brier": self.brier,
                "calibration_error": self.calibration_error,
                "negative_control_positive_rate": (
                    self.negative_control_positive_rate
                ),
                "qualified_primary": self.qualified_primary,
                "qualified_control": self.qualified_control,
                "fingerprint": self.fingerprint,
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
    qualified_domain_count: int
    qualified_control_domain_count: int
    mean_probability: float | None
    empirical_rate: float | None
    wilson_95: tuple[float, float] | None
    brier: float | None
    calibration_error: float | None
    negative_control_positive_rate: float | None
    worst_domain_brier: float | None
    minimum_domain_empirical_rate: float | None
    worst_domain_control_positive_rate: float | None
    domain_reports: tuple[TopologyBridgeDomainReport, ...]
    reasons: tuple[str, ...]
    fingerprint: str

    def as_json(self) -> dict[str, Any]:
        return json_safe(
            {
                "report_id": self.report_id,
                "candidate_id": self.candidate_id,
                "candidate_fingerprint": self.candidate_fingerprint,
                "left_key": self.left_key,
                "right_key": self.right_key,
                "kind": self.kind.value,
                "status": self.status.value,
                "trial_count": self.trial_count,
                "independent_run_count": self.independent_run_count,
                "domain_count": self.domain_count,
                "negative_control_count": self.negative_control_count,
                "qualified_domain_count": self.qualified_domain_count,
                "qualified_control_domain_count": (
                    self.qualified_control_domain_count
                ),
                "mean_probability": self.mean_probability,
                "empirical_rate": self.empirical_rate,
                "wilson_95": self.wilson_95,
                "brier": self.brier,
                "calibration_error": self.calibration_error,
                "negative_control_positive_rate": (
                    self.negative_control_positive_rate
                ),
                "worst_domain_brier": self.worst_domain_brier,
                "minimum_domain_empirical_rate": (
                    self.minimum_domain_empirical_rate
                ),
                "worst_domain_control_positive_rate": (
                    self.worst_domain_control_positive_rate
                ),
                "domain_reports": [
                    item.as_json() for item in self.domain_reports
                ],
                "reasons": list(self.reasons),
                "fingerprint": self.fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class LearnedTopologyRule:
    candidate_id: str
    candidate_fingerprint: str
    report_id: str
    report_fingerprint: str
    rule: LensInteractionRule
    bridge_quality: float
    fingerprint: str

    def __post_init__(self) -> None:
        for name in (
            "candidate_id",
            "candidate_fingerprint",
            "report_id",
            "report_fingerprint",
            "fingerprint",
        ):
            value = str(getattr(self, name)).strip()
            if not value:
                raise AgentContractError(f"{name} is required")
            object.__setattr__(self, name, value)
        if not isinstance(self.rule, LensInteractionRule):
            raise TypeError("rule must be LensInteractionRule")
        object.__setattr__(
            self,
            "bridge_quality",
            probability("bridge_quality", self.bridge_quality),
        )

    def as_json(self) -> dict[str, Any]:
        return json_safe(
            {
                "candidate_id": self.candidate_id,
                "candidate_fingerprint": self.candidate_fingerprint,
                "report_id": self.report_id,
                "report_fingerprint": self.report_fingerprint,
                "bridge_quality": self.bridge_quality,
                "rule": {
                    "left_key": self.rule.left_key,
                    "right_key": self.rule.right_key,
                    "kind": self.rule.kind.value,
                    "rationale": self.rule.rationale,
                    "question": self.rule.question,
                    "predictive_effect": self.rule.predictive_effect,
                    "symmetric": self.rule.symmetric,
                    "tangent_axis_hint": self.rule.tangent_axis_hint,
                    "metadata": dict(self.rule.metadata),
                },
                "fingerprint": self.fingerprint,
            }
        )


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

    def as_json(self) -> dict[str, Any]:
        return json_safe(
            {
                "prediction_count": self.prediction_count,
                "unresolved_prediction_count": (
                    self.unresolved_prediction_count
                ),
                "trial_count": self.trial_count,
                "tested_bridge_count": self.tested_bridge_count,
                "active_report_ids": list(self.active_report_ids),
                "restricted_report_ids": list(
                    self.restricted_report_ids
                ),
                "rejected_report_ids": list(self.rejected_report_ids),
                "candidate_report_ids": list(self.candidate_report_ids),
                "ambiguous_active_candidate_ids": list(
                    self.ambiguous_active_candidate_ids
                ),
                "learned_rule_keys": [
                    list(item) for item in self.learned_rule_keys
                ],
                "fingerprint": self.fingerprint,
            }
        )


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
        self._prediction_slots: dict[
            tuple[str, str, str, str, bool],
            str,
        ] = {}
        self._trials: dict[str, TopologyBridgeTrial] = {}
        self._trials_by_candidate_kind: dict[
            tuple[str, str],
            set[str],
        ] = {}
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

    def declare_candidate_prediction(
        self,
        candidate_id: str,
        *,
        kind: LensInteractionKind,
        predicted_probability: float,
        domain: str,
        independent_run: str,
        predicted_at: float,
        negative_control: bool = False,
        source_finding_ids: Sequence[str] = (),
        source_forecast_ids: Sequence[str] = (),
        evidence_ids: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> TopologyBridgePrediction:
        """Construct and declare one contract-bound experiment prediction."""

        candidate = self._candidates.get(str(candidate_id).strip())
        if candidate is None:
            raise AgentContractError(
                "unknown semantic topology bridge candidate"
            )
        kind_value = (
            kind
            if isinstance(kind, LensInteractionKind)
            else LensInteractionKind(str(kind))
        )
        domain_value = bounded_text(
            "domain",
            domain,
            maximum=256,
        ).casefold()
        run_value = bounded_text(
            "independent_run",
            independent_run,
            maximum=512,
        )
        predicted_time = finite_number("predicted_at", predicted_at)
        if predicted_time < 0:
            raise AgentContractError(
                "topology bridge prediction time must be non-negative"
            )
        candidate_fingerprint = self.candidate_fingerprint(candidate)
        normalized_findings = tuple(
            sorted(
                {
                    str(value).strip()
                    for value in source_finding_ids
                    if str(value).strip()
                }
            )
        )
        normalized_forecasts = tuple(
            sorted(
                {
                    str(value).strip()
                    for value in source_forecast_ids
                    if str(value).strip()
                }
            )
        )
        normalized_evidence = tuple(
            sorted(
                {
                    str(value).strip()
                    for value in evidence_ids
                    if str(value).strip()
                }
            )
        )
        metadata_value = json_safe(dict(metadata or {}))
        prediction_id = stable_id(
            "semantic-topology-prediction",
            {
                "candidate": candidate_fingerprint,
                "kind": kind_value.value,
                "probability": probability(
                    "predicted_probability",
                    predicted_probability,
                ),
                "domain": domain_value,
                "run": run_value,
                "predicted_at": predicted_time,
                "negative_control": negative_control,
                "findings": normalized_findings,
                "forecasts": normalized_forecasts,
                "evidence": normalized_evidence,
                "metadata": metadata_value,
            },
            length=32,
        )
        prediction = TopologyBridgePrediction(
            prediction_id=prediction_id,
            candidate_id=candidate.candidate_id,
            candidate_fingerprint=candidate_fingerprint,
            left_key=candidate.left_key,
            right_key=candidate.right_key,
            kind=kind_value,
            predicted_probability=predicted_probability,
            domain=domain_value,
            independent_run=run_value,
            predicted_at=predicted_time,
            negative_control=negative_control,
            source_finding_ids=normalized_findings,
            source_forecast_ids=normalized_forecasts,
            evidence_ids=normalized_evidence,
            metadata=metadata_value,
        )
        return self.declare(prediction)

    def unresolved_predictions(
        self,
        *,
        candidate_id: str | None = None,
    ) -> tuple[TopologyBridgePrediction, ...]:
        """Return declared predictions that do not yet have an outcome."""

        candidate_key = (
            str(candidate_id).strip()
            if candidate_id is not None
            else None
        )
        with self._lock:
            values = [
                prediction
                for prediction_id, prediction in self._predictions.items()
                if prediction_id not in self._resolved_predictions
                and (
                    candidate_key is None
                    or prediction.candidate_id == candidate_key
                )
            ]
        return tuple(
            sorted(values, key=lambda item: item.prediction_id)
        )

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

            slot_prediction_id = self._prediction_slots.get(
                prediction.slot_key
            )
            if slot_prediction_id is not None:
                prior = self._predictions[slot_prediction_id]
                if prior.fingerprint == prediction.fingerprint:
                    return prior
                raise AgentContractError(
                    "topology bridge experiment slot already has a "
                    "different predeclared prediction"
                )

            if len(self._predictions) >= self.policy.maximum_predictions:
                raise AgentContractError(
                    "topology bridge prediction capacity exhausted"
                )
            unresolved_count = (
                len(self._predictions) - len(self._resolved_predictions)
            )
            if (
                unresolved_count
                >= self.policy.maximum_unresolved_predictions
            ):
                raise AgentContractError(
                    "topology bridge unresolved prediction capacity exhausted"
                )
            self._predictions[prediction.prediction_id] = prediction
            self._prediction_slots[prediction.slot_key] = (
                prediction.prediction_id
            )
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

            if len(self._trials) >= self.policy.maximum_trials:
                raise AgentContractError(
                    "topology bridge trial capacity exhausted"
                )
            self._trials[trial.trial_id] = trial
            index_key = (
                trial.candidate_id,
                trial.kind.value,
            )
            self._trials_by_candidate_kind.setdefault(
                index_key,
                set(),
            ).add(trial.trial_id)
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
            if kind_value is not None:
                trial_ids = self._trials_by_candidate_kind.get(
                    (candidate_key, kind_value.value),
                    set(),
                )
            else:
                trial_ids = {
                    trial_id
                    for (indexed_candidate, _), ids
                    in self._trials_by_candidate_kind.items()
                    if indexed_candidate == candidate_key
                    for trial_id in ids
                }
            values = [
                self._trials[trial_id]
                for trial_id in trial_ids
            ]
        return tuple(
            sorted(values, key=lambda item: item.trial_id)
        )

    def _domain_reports(
        self,
        primary: Sequence[TopologyBridgeTrial],
        controls: Sequence[TopologyBridgeTrial],
    ) -> tuple[TopologyBridgeDomainReport, ...]:
        domains = sorted(
            {
                item.domain for item in (*tuple(primary), *tuple(controls))
            }
        )
        reports: list[TopologyBridgeDomainReport] = []
        for domain in domains:
            domain_primary = [
                item for item in primary if item.domain == domain
            ]
            domain_controls = [
                item for item in controls if item.domain == domain
            ]
            if domain_primary:
                probabilities = [
                    item.predicted_probability
                    for item in domain_primary
                ]
                outcomes = [item.outcome for item in domain_primary]
                positive_count = sum(outcomes)
                mean_probability = sum(probabilities) / len(probabilities)
                empirical_rate = positive_count / len(domain_primary)
                interval = wilson_interval(
                    positive_count,
                    len(domain_primary),
                )
                brier = brier_score(probabilities, outcomes)
                calibration_error = expected_calibration_error(
                    probabilities,
                    outcomes,
                    bins=min(10, len(domain_primary)),
                )
            else:
                mean_probability = None
                empirical_rate = None
                interval = None
                brier = None
                calibration_error = None
            control_rate = (
                None
                if not domain_controls
                else sum(item.outcome for item in domain_controls)
                / len(domain_controls)
            )
            primary_run_count = len(
                {
                    item.independent_run
                    for item in domain_primary
                }
            )
            control_run_count = len(
                {
                    item.independent_run
                    for item in domain_controls
                }
            )
            qualified_primary = (
                len(domain_primary)
                >= self.policy.minimum_trials_per_domain
                and primary_run_count
                >= self.policy.minimum_independent_runs_per_domain
            )
            qualified_control = (
                len(domain_controls)
                >= self.policy.minimum_controls_per_domain
                and control_run_count
                >= self.policy.minimum_control_runs_per_domain
            )
            fingerprint = stable_fingerprint(
                {
                    "domain": domain,
                    "primary": [
                        item.fingerprint for item in domain_primary
                    ],
                    "controls": [
                        item.fingerprint for item in domain_controls
                    ],
                    "metrics": {
                        "mean_probability": mean_probability,
                        "empirical_rate": empirical_rate,
                        "wilson_95": interval,
                        "brier": brier,
                        "calibration_error": calibration_error,
                        "control_positive_rate": control_rate,
                    },
                    "qualified_primary": qualified_primary,
                    "qualified_control": qualified_control,
                    "policy": self.policy.fingerprint,
                }
            )
            reports.append(
                TopologyBridgeDomainReport(
                    domain=domain,
                    trial_count=len(domain_primary),
                    independent_run_count=primary_run_count,
                    negative_control_count=len(domain_controls),
                    negative_control_run_count=control_run_count,
                    mean_probability=mean_probability,
                    empirical_rate=empirical_rate,
                    wilson_95=interval,
                    brier=brier,
                    calibration_error=calibration_error,
                    negative_control_positive_rate=control_rate,
                    qualified_primary=qualified_primary,
                    qualified_control=qualified_control,
                    fingerprint=fingerprint,
                )
            )
        return tuple(reports)

    def _report_status(
        self,
        *,
        trial_count: int,
        independent_runs: int,
        qualified_domains: int,
        negative_control_count: int,
        qualified_control_domains: int,
        brier: float,
        calibration_error: float,
        empirical_rate: float,
        negative_control_positive_rate: float | None,
        worst_domain_brier: float | None,
        minimum_domain_empirical_rate: float | None,
        worst_domain_control_positive_rate: float | None,
    ) -> tuple[TopologyBridgeStatus, tuple[str, ...]]:
        reasons: list[str] = []
        if trial_count < self.policy.minimum_trials:
            reasons.append("insufficient_trials")
        if independent_runs < self.policy.minimum_independent_runs:
            reasons.append("insufficient_independent_runs")
        if qualified_domains < self.policy.minimum_domains:
            reasons.append("insufficient_domain_replication")
        if negative_control_count < self.policy.minimum_negative_controls:
            reasons.append("insufficient_negative_controls")
        if (
            qualified_control_domains
            < self.policy.minimum_control_domains
        ):
            reasons.append("insufficient_control_domain_replication")

        enough_for_rejection = (
            trial_count >= self.policy.minimum_trials
            and qualified_domains >= self.policy.minimum_domains
        )
        if enough_for_rejection and brier >= self.policy.reject_brier:
            reasons.append("brier_rejection_threshold")
        if (
            enough_for_rejection
            and calibration_error >= self.policy.reject_ece
        ):
            reasons.append("calibration_rejection_threshold")
        if (
            enough_for_rejection
            and empirical_rate <= self.policy.reject_empirical_rate
        ):
            reasons.append("empirical_rate_rejection_threshold")
        if (
            enough_for_rejection
            and worst_domain_brier is not None
            and worst_domain_brier >= self.policy.reject_domain_brier
        ):
            reasons.append("domain_brier_rejection_threshold")
        if (
            enough_for_rejection
            and minimum_domain_empirical_rate is not None
            and minimum_domain_empirical_rate
            <= self.policy.reject_domain_empirical_rate
        ):
            reasons.append("domain_empirical_rate_rejection_threshold")
        rejection = any(
            reason.endswith("rejection_threshold")
            for reason in reasons
        )
        if rejection:
            return TopologyBridgeStatus.REJECTED, tuple(reasons)

        negative_control_failed = (
            (
                negative_control_positive_rate is not None
                and negative_control_count
                >= self.policy.minimum_negative_controls
                and negative_control_positive_rate
                > self.policy.maximum_negative_control_positive_rate
            )
            or (
                worst_domain_control_positive_rate is not None
                and qualified_control_domains
                >= self.policy.minimum_control_domains
                and worst_domain_control_positive_rate
                > self.policy.maximum_domain_control_positive_rate
            )
        )
        if negative_control_failed:
            reasons.append("negative_control_failure")

        domain_transfer_failed = (
            (
                worst_domain_brier is not None
                and qualified_domains >= self.policy.minimum_domains
                and worst_domain_brier
                > self.policy.maximum_domain_brier
            )
            or (
                minimum_domain_empirical_rate is not None
                and qualified_domains >= self.policy.minimum_domains
                and minimum_domain_empirical_rate
                < self.policy.minimum_domain_empirical_rate
            )
        )
        if domain_transfer_failed:
            reasons.append("domain_transfer_failure")

        complete = (
            trial_count >= self.policy.minimum_trials
            and independent_runs >= self.policy.minimum_independent_runs
            and qualified_domains >= self.policy.minimum_domains
            and negative_control_count
            >= self.policy.minimum_negative_controls
            and qualified_control_domains
            >= self.policy.minimum_control_domains
        )
        calibrated = (
            brier <= self.policy.maximum_brier
            and calibration_error <= self.policy.maximum_ece
            and empirical_rate >= self.policy.minimum_empirical_rate
            and not negative_control_failed
            and not domain_transfer_failed
        )
        if complete and calibrated:
            reasons.append("replicated_calibrated_bridge")
            return TopologyBridgeStatus.ACTIVE, tuple(reasons)
        if complete:
            reasons.append(
                "replication_complete_but_promotion_thresholds_unmet"
            )
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
                qualified_domain_count=0,
                qualified_control_domain_count=0,
                mean_probability=None,
                empirical_rate=None,
                wilson_95=None,
                brier=None,
                calibration_error=None,
                negative_control_positive_rate=None,
                worst_domain_brier=None,
                minimum_domain_empirical_rate=None,
                worst_domain_control_positive_rate=None,
                domain_reports=(),
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
                qualified_domain_count=0,
                qualified_control_domain_count=len(
                    {
                        item.domain
                        for item in controls
                        if sum(
                            1
                            for control in controls
                            if control.domain == item.domain
                        )
                        >= self.policy.minimum_controls_per_domain
                    }
                ),
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
                worst_domain_brier=None,
                minimum_domain_empirical_rate=None,
                worst_domain_control_positive_rate=(
                    None
                    if not controls
                    else max(
                        sum(
                            control.outcome
                            for control in controls
                            if control.domain == domain
                        )
                        / sum(
                            1
                            for control in controls
                            if control.domain == domain
                        )
                        for domain in {
                            item.domain for item in controls
                        }
                    )
                ),
                domain_reports=self._domain_reports((), controls),
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
        domain_reports = self._domain_reports(primary, controls)
        qualified_primary_reports = [
            item for item in domain_reports if item.qualified_primary
        ]
        qualified_control_reports = [
            item for item in domain_reports if item.qualified_control
        ]
        worst_domain_brier = (
            None
            if not qualified_primary_reports
            else max(
                item.brier
                for item in qualified_primary_reports
                if item.brier is not None
            )
        )
        minimum_domain_empirical_rate = (
            None
            if not qualified_primary_reports
            else min(
                item.empirical_rate
                for item in qualified_primary_reports
                if item.empirical_rate is not None
            )
        )
        worst_domain_control_positive_rate = (
            None
            if not qualified_control_reports
            else max(
                item.negative_control_positive_rate
                for item in qualified_control_reports
                if item.negative_control_positive_rate is not None
            )
        )
        status, reasons = self._report_status(
            trial_count=len(primary),
            independent_runs=len(runs),
            qualified_domains=len(qualified_primary_reports),
            negative_control_count=len(controls),
            qualified_control_domains=len(qualified_control_reports),
            brier=brier,
            calibration_error=calibration_error,
            empirical_rate=empirical_rate,
            negative_control_positive_rate=control_rate,
            worst_domain_brier=worst_domain_brier,
            minimum_domain_empirical_rate=minimum_domain_empirical_rate,
            worst_domain_control_positive_rate=(
                worst_domain_control_positive_rate
            ),
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
                    "qualified_domain_count": len(
                        qualified_primary_reports
                    ),
                    "qualified_control_domain_count": len(
                        qualified_control_reports
                    ),
                    "worst_domain_brier": worst_domain_brier,
                    "minimum_domain_empirical_rate": (
                        minimum_domain_empirical_rate
                    ),
                    "worst_domain_control_positive_rate": (
                        worst_domain_control_positive_rate
                    ),
                    "domain_reports": [
                        item.fingerprint for item in domain_reports
                    ],
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
            qualified_domain_count=len(qualified_primary_reports),
            qualified_control_domain_count=len(
                qualified_control_reports
            ),
            mean_probability=mean_probability,
            empirical_rate=empirical_rate,
            wilson_95=interval,
            brier=brier,
            calibration_error=calibration_error,
            negative_control_positive_rate=control_rate,
            worst_domain_brier=worst_domain_brier,
            minimum_domain_empirical_rate=minimum_domain_empirical_rate,
            worst_domain_control_positive_rate=(
                worst_domain_control_positive_rate
            ),
            domain_reports=domain_reports,
            reasons=reasons,
            fingerprint=fingerprint,
        )

    def reports(self) -> tuple[TopologyBridgeReport, ...]:
        with self._lock:
            identities = tuple(
                sorted(
                    (
                        candidate_id,
                        LensInteractionKind(kind_value),
                    )
                    for (candidate_id, kind_value), trial_ids
                    in self._trials_by_candidate_kind.items()
                    if trial_ids
                )
            )
        return tuple(
            self.report(candidate_id, kind)
            for candidate_id, kind in identities
        )

    @staticmethod
    def _bridge_quality(
        report: TopologyBridgeReport,
    ) -> float:
        """Conservative quality floor across validated bridge dimensions."""

        components: list[float] = []
        if report.empirical_rate is not None:
            components.append(report.empirical_rate)
        if report.brier is not None:
            components.append(1.0 - report.brier)
        if report.calibration_error is not None:
            components.append(1.0 - report.calibration_error)
        if report.negative_control_positive_rate is not None:
            components.append(
                1.0 - report.negative_control_positive_rate
            )
        if report.minimum_domain_empirical_rate is not None:
            components.append(
                report.minimum_domain_empirical_rate
            )
        if report.worst_domain_brier is not None:
            components.append(1.0 - report.worst_domain_brier)
        if (
            report.worst_domain_control_positive_rate
            is not None
        ):
            components.append(
                1.0 - report.worst_domain_control_positive_rate
            )
        if not components:
            return 0.0
        return max(0.0, min(1.0, min(components)))

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
                    "bridge_quality": self._bridge_quality(report),
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
                    bridge_quality=self._bridge_quality(report),
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

    def diagnostics(
        self,
        *,
        candidate_id: str | None = None,
        kind: LensInteractionKind | None = None,
        limit: int = 100,
    ) -> Mapping[str, Any]:
        """Return bounded operational diagnostics for bridge-learning state."""

        maximum = positive_int("limit", limit, maximum=10_000)
        candidate_key = (
            str(candidate_id).strip()
            if candidate_id is not None
            else None
        )
        if candidate_key is not None and candidate_key not in self._candidates:
            raise AgentContractError(
                "unknown semantic topology bridge candidate"
            )
        kind_value = (
            kind
            if kind is None or isinstance(kind, LensInteractionKind)
            else LensInteractionKind(str(kind))
        )

        with self._lock:
            reports = [
                item
                for item in self.reports()
                if (
                    candidate_key is None
                    or item.candidate_id == candidate_key
                )
                and (
                    kind_value is None
                    or item.kind is kind_value
                )
            ]
            reports.sort(
                key=lambda item: (
                    item.candidate_id,
                    item.kind.value,
                )
            )
            learned, snapshot = self.evaluate()
            learned_filtered = [
                item
                for item in learned
                if (
                    candidate_key is None
                    or item.candidate_id == candidate_key
                )
                and (
                    kind_value is None
                    or item.rule.kind is kind_value
                )
            ]
            unresolved = [
                item
                for item in self.unresolved_predictions(
                    candidate_id=candidate_key,
                )
                if (
                    kind_value is None
                    or item.kind is kind_value
                )
            ]
            candidate_payloads = []
            candidate_values = (
                [self._candidates[candidate_key]]
                if candidate_key is not None
                else sorted(
                    self._candidates.values(),
                    key=lambda item: (
                        -item.score,
                        item.candidate_id,
                    ),
                )
            )
            for candidate in candidate_values[:maximum]:
                candidate_payloads.append(
                    {
                        "candidate_id": candidate.candidate_id,
                        "candidate_fingerprint": (
                            self.candidate_fingerprint(candidate)
                        ),
                        "left_key": candidate.left_key,
                        "right_key": candidate.right_key,
                        "left_family": candidate.left_family.value,
                        "right_family": candidate.right_family.value,
                        "score": candidate.score,
                        "cue_overlap": candidate.cue_overlap,
                        "role_novelty": candidate.role_novelty,
                        "cross_family": candidate.cross_family,
                        "shared_cues": list(candidate.shared_cues),
                        "rationale": candidate.rationale,
                    }
                )

            payload = {
                "contract_fingerprint": self.contract_fingerprint,
                "state_fingerprint": self.fingerprint,
                "snapshot": snapshot.as_json(),
                "candidates": candidate_payloads,
                "reports": [
                    item.as_json() for item in reports[:maximum]
                ],
                "learned_rules": [
                    item.as_json()
                    for item in learned_filtered[:maximum]
                ],
                "unresolved_predictions": [
                    item.as_json() for item in unresolved[:maximum]
                ],
                "truncated": {
                    "candidates": len(candidate_values) > maximum,
                    "reports": len(reports) > maximum,
                    "learned_rules": len(learned_filtered) > maximum,
                    "unresolved_predictions": len(unresolved) > maximum,
                },
                "invariants": {
                    "diagnostics_are_not_evidence": True,
                    "learned_rules_remain_interpretive": True,
                    "static_topology_contract_is_immutable": True,
                    "outcomes_require_predeclared_predictions": True,
                },
            }
        return json_safe(payload)

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

                candidate_trial_ids = {
                    trial_id
                    for (indexed_candidate, _), trial_ids
                    in self._trials_by_candidate_kind.items()
                    if indexed_candidate == candidate.candidate_id
                    for trial_id in trial_ids
                }
                candidate_trials = [
                    self._trials[trial_id]
                    for trial_id in candidate_trial_ids
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
                domain_trial_counts = {
                    domain: sum(
                        1 for item in primary if item.domain == domain
                    )
                    for domain in {item.domain for item in primary}
                }
                control_domain_counts = {
                    domain: sum(
                        1 for item in controls if item.domain == domain
                    )
                    for domain in {item.domain for item in controls}
                }
                domain_run_counts = {
                    domain: len(
                        {
                            item.independent_run
                            for item in primary
                            if item.domain == domain
                        }
                    )
                    for domain in domain_trial_counts
                }
                control_domain_run_counts = {
                    domain: len(
                        {
                            item.independent_run
                            for item in controls
                            if item.domain == domain
                        }
                    )
                    for domain in control_domain_counts
                }
                qualified_domain_count = sum(
                    count >= self.policy.minimum_trials_per_domain
                    and domain_run_counts.get(domain, 0)
                    >= self.policy.minimum_independent_runs_per_domain
                    for domain, count in domain_trial_counts.items()
                )
                qualified_control_domain_count = sum(
                    count >= self.policy.minimum_controls_per_domain
                    and control_domain_run_counts.get(domain, 0)
                    >= self.policy.minimum_control_runs_per_domain
                    for domain, count in control_domain_counts.items()
                )
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
                    qualified_domain_count
                    / self.policy.minimum_domains,
                )
                control_count_coverage = min(
                    1.0,
                    len(controls) / self.policy.minimum_negative_controls,
                )
                control_domain_coverage = min(
                    1.0,
                    qualified_control_domain_count
                    / self.policy.minimum_control_domains,
                )
                control_coverage = min(
                    control_count_coverage,
                    control_domain_coverage,
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
                        "domain_count": len(domain_trial_counts),
                        "domain_run_counts": dict(domain_run_counts),
                        "qualified_domain_count": (
                            qualified_domain_count
                        ),
                        "control_domain_count": len(
                            control_domain_counts
                        ),
                        "control_domain_run_counts": dict(
                            control_domain_run_counts
                        ),
                        "qualified_control_domain_count": (
                            qualified_control_domain_count
                        ),
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
        staged_slots: dict[
            tuple[str, str, str, str, bool],
            str,
        ] = {}
        for prediction in restored.predictions:
            self._validate_prediction_candidate(prediction)
            if prediction.prediction_id in staged_predictions:
                raise AgentContractError(
                    "duplicate topology bridge prediction during restore"
                )
            prior_slot = staged_slots.get(prediction.slot_key)
            if prior_slot is not None:
                raise AgentContractError(
                    "topology learning state contains competing predictions "
                    "for one experiment slot"
                )
            staged_predictions[prediction.prediction_id] = prediction
            staged_slots[prediction.slot_key] = prediction.prediction_id

        if len(staged_predictions) > self.policy.maximum_predictions:
            raise AgentContractError(
                "restored topology prediction capacity exceeded"
            )

        staged_trials: dict[str, TopologyBridgeTrial] = {}
        staged_trial_index: dict[tuple[str, str], set[str]] = {}
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
            staged_trial_index.setdefault(
                (trial.candidate_id, trial.kind.value),
                set(),
            ).add(trial.trial_id)
            staged_resolved[trial.prediction_id] = trial.trial_id

        if len(staged_trials) > self.policy.maximum_trials:
            raise AgentContractError(
                "restored topology trial capacity exceeded"
            )
        if (
            len(staged_predictions) - len(staged_resolved)
            > self.policy.maximum_unresolved_predictions
        ):
            raise AgentContractError(
                "restored unresolved topology prediction capacity exceeded"
            )

        with self._lock:
            self._predictions = staged_predictions
            self._prediction_slots = staged_slots
            self._trials = staged_trials
            self._trials_by_candidate_kind = staged_trial_index
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
    "TopologyBridgeDomainReport",
    "TopologyBridgePolicy",
    "TopologyBridgePrediction",
    "TopologyBridgeReport",
    "TopologyBridgeStatus",
    "TopologyBridgeTrial",
]
