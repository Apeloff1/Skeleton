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
class TopologyBridgeTrial:
    trial_id: str
    candidate_id: str
    candidate_fingerprint: str
    left_key: str
    right_key: str
    kind: LensInteractionKind
    predicted_probability: float
    outcome: bool
    domain: str
    independent_run: str
    negative_control: bool = False
    source_finding_ids: tuple[str, ...] = ()
    source_forecast_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "trial_id",
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
            raise AgentContractError("topology bridge trial requires distinct lenses")
        if not isinstance(self.kind, LensInteractionKind):
            object.__setattr__(self, "kind", LensInteractionKind(str(self.kind)))
        object.__setattr__(
            self,
            "predicted_probability",
            probability("predicted_probability", self.predicted_probability),
        )
        if not isinstance(self.outcome, bool):
            raise AgentContractError("topology bridge trial outcome must be boolean")
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
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def bridge_key(self) -> tuple[str, str]:
        return tuple(sorted((self.left_key, self.right_key)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "trial": self.trial_id,
                "candidate": self.candidate_id,
                "candidate_fingerprint": self.candidate_fingerprint,
                "bridge": self.bridge_key,
                "kind": self.kind.value,
                "probability": self.predicted_probability,
                "outcome": self.outcome,
                "domain": self.domain,
                "run": self.independent_run,
                "negative_control": self.negative_control,
                "findings": self.source_finding_ids,
                "forecasts": self.source_forecast_ids,
                "evidence": self.evidence_ids,
                "metadata": dict(self.metadata),
            }
        )


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
        self._trials: dict[str, TopologyBridgeTrial] = {}
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

    def record(self, trial: TopologyBridgeTrial) -> TopologyBridgeTrial:
        if not isinstance(trial, TopologyBridgeTrial):
            raise TypeError("trial must be TopologyBridgeTrial")
        candidate = self._candidates.get(trial.candidate_id)
        if candidate is None:
            raise AgentContractError("unknown semantic topology bridge candidate")
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
            existing = self._trials.get(trial.trial_id)
            if existing is not None:
                if existing.fingerprint != trial.fingerprint:
                    raise AgentContractError(
                        f"topology bridge trial id reused differently: {trial.trial_id}"
                    )
                return existing
            self._trials[trial.trial_id] = trial
        return trial

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

    def learned_rules(self) -> tuple[LearnedTopologyRule, ...]:
        learned: list[LearnedTopologyRule] = []
        active_by_candidate: dict[str, list[TopologyBridgeReport]] = {}
        for report in self.reports():
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
                candidate.right_family if candidate.cross_family else candidate.left_family,
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

    def snapshot(self) -> SemanticTopologyLearningSnapshot:
        reports = self.reports()
        learned = self.learned_rules()
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
        with self._lock:
            trial_count = len(self._trials)
        fingerprint = stable_fingerprint(
            {
                "topology": self.topology.fingerprint,
                "policy": self.policy.fingerprint,
                "reports": [item.fingerprint for item in reports],
                "learned": [item.fingerprint for item in learned],
                "ambiguous_active_candidates": ambiguous,
                "trial_count": trial_count,
            }
        )
        return SemanticTopologyLearningSnapshot(
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
            trials = [
                (trial_id, trial.fingerprint)
                for trial_id, trial in sorted(self._trials.items())
            ]
        return stable_fingerprint(
            {
                "contract": self.contract_fingerprint,
                "trials": trials,
            }
        )


__all__ = [
    "LearnedTopologyRule",
    "SemanticTopologyLearningLab",
    "SemanticTopologyLearningSnapshot",
    "TopologyBridgePolicy",
    "TopologyBridgeReport",
    "TopologyBridgeStatus",
    "TopologyBridgeTrial",
]
