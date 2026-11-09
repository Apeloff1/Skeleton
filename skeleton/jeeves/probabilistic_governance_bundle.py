"""End-to-end evidence alignment for Jeeves probabilistic governance.

This layer builds point/distributional promotion evidence, stratified conformal
governance evidence, and the two-key joint decision from their source reports.
Before issuing its own evidence decision it verifies that every conformal-scored
target belongs to the ensemble backtest and carries the same realized value.

The bundle has no activation authority.  It exists to prevent a subtle custody
failure: independently valid evidence artifacts from different target sets must
not be composable merely because their sample counts happen to look similar.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from .probabilistic_calibration import CalibrationReport
from .probabilistic_conformal_stratified import StratifiedConformalReport
from .probabilistic_contracts import (
    ProbabilisticPromotionDecision,
    ProbabilisticPromotionGate,
    evaluate_probabilistic_promotion,
    validate_probabilistic_promotion_decision,
)
from .probabilistic_ensemble import BayesianEnsembleReport
from .probabilistic_governance import (
    ConformalGovernanceDecision,
    ConformalGovernanceGate,
    evaluate_conformal_governance,
    validate_conformal_governance_decision,
)
from .probabilistic_joint_governance import (
    JointProbabilisticGovernanceDecision,
    JointProbabilisticGovernanceGate,
    evaluate_joint_probabilistic_governance,
    validate_joint_probabilistic_governance_decision,
)
from .probabilistic_state_space import StateSpaceError


@dataclass(frozen=True, slots=True)
class ProbabilisticGovernanceBundleGate:
    """Evidence-alignment requirements above the two child governance planes."""

    min_aligned_target_ratio: float = 0.50
    max_actual_delta: float = 1e-12

    def __post_init__(self) -> None:
        _open_closed_unit("min_aligned_target_ratio", self.min_aligned_target_ratio)
        delta = _finite("max_actual_delta", self.max_actual_delta)
        if delta < 0.0:
            raise StateSpaceError(
                "max_actual_delta must be non-negative",
                context={"reason": "invalid_governance_bundle_gate"},
            )


@dataclass(frozen=True, slots=True)
class ProbabilisticGovernanceBundle:
    """Integrity-bound, target-aligned probabilistic governance evidence."""

    eligible: bool
    reasons: tuple[str, ...]
    probabilistic: ProbabilisticPromotionDecision
    conformal: ConformalGovernanceDecision
    joint: JointProbabilisticGovernanceDecision
    ensemble_targets: int
    conformal_targets: int
    aligned_targets: int
    aligned_target_ratio: float
    aligned_target_indices: tuple[int, ...]
    ensemble_target_fingerprint: str
    conformal_target_fingerprint: str
    gate_fingerprint: str
    fingerprint: str


def evaluate_probabilistic_governance_bundle(
    ensemble: BayesianEnsembleReport,
    calibration: CalibrationReport,
    conformal_report: StratifiedConformalReport,
    *,
    probabilistic_gate: ProbabilisticPromotionGate | None = None,
    conformal_gate: ConformalGovernanceGate | None = None,
    joint_gate: JointProbabilisticGovernanceGate | None = None,
    bundle_gate: ProbabilisticGovernanceBundleGate | None = None,
) -> ProbabilisticGovernanceBundle:
    """Build and align all probabilistic governance evidence planes."""

    actual_gate = bundle_gate or ProbabilisticGovernanceBundleGate()
    probabilistic = evaluate_probabilistic_promotion(
        ensemble,
        calibration,
        gate=probabilistic_gate,
    )
    conformal = evaluate_conformal_governance(
        conformal_report,
        gate=conformal_gate,
    )
    joint = evaluate_joint_probabilistic_governance(
        probabilistic,
        conformal,
        gate=joint_gate,
    )

    ensemble_pairs = _ensemble_target_pairs(ensemble)
    conformal_pairs = _conformal_target_pairs(conformal_report)
    aligned_indices = _validate_target_alignment(
        ensemble_pairs,
        conformal_pairs,
        max_actual_delta=actual_gate.max_actual_delta,
    )
    aligned_ratio = len(aligned_indices) / len(ensemble_pairs)

    reasons: list[str] = []
    if not joint.eligible:
        reasons.append("joint_probabilistic_governance_ineligible")
    if aligned_ratio < actual_gate.min_aligned_target_ratio:
        reasons.append("aligned_target_ratio_below_gate")
    eligible = not reasons
    if eligible:
        reasons.append("probabilistic_governance_bundle_passed")

    ensemble_target_fingerprint = _target_fingerprint(
        "jeeves.ensemble-targets.v1",
        ensemble_pairs,
    )
    conformal_target_fingerprint = _target_fingerprint(
        "jeeves.conformal-targets.v1",
        conformal_pairs,
    )
    gate_fingerprint = _gate_fingerprint(actual_gate)
    fingerprint = _bundle_fingerprint(
        eligible=eligible,
        reasons=tuple(reasons),
        probabilistic_fingerprint=probabilistic.fingerprint,
        conformal_fingerprint=conformal.fingerprint,
        joint_fingerprint=joint.fingerprint,
        ensemble_targets=len(ensemble_pairs),
        conformal_targets=len(conformal_pairs),
        aligned_targets=len(aligned_indices),
        aligned_target_ratio=aligned_ratio,
        aligned_target_indices=aligned_indices,
        ensemble_target_fingerprint=ensemble_target_fingerprint,
        conformal_target_fingerprint=conformal_target_fingerprint,
        gate_fingerprint=gate_fingerprint,
    )
    return ProbabilisticGovernanceBundle(
        eligible=eligible,
        reasons=tuple(reasons),
        probabilistic=probabilistic,
        conformal=conformal,
        joint=joint,
        ensemble_targets=len(ensemble_pairs),
        conformal_targets=len(conformal_pairs),
        aligned_targets=len(aligned_indices),
        aligned_target_ratio=aligned_ratio,
        aligned_target_indices=aligned_indices,
        ensemble_target_fingerprint=ensemble_target_fingerprint,
        conformal_target_fingerprint=conformal_target_fingerprint,
        gate_fingerprint=gate_fingerprint,
        fingerprint=fingerprint,
    )


def validate_probabilistic_governance_bundle(
    bundle: ProbabilisticGovernanceBundle,
) -> None:
    """Reject malformed or tampered bundled governance evidence."""

    if not isinstance(bundle, ProbabilisticGovernanceBundle):
        raise StateSpaceError(
            "bundle must be a ProbabilisticGovernanceBundle",
            context={"reason": "invalid_governance_bundle"},
        )
    if not isinstance(bundle.eligible, bool):
        raise StateSpaceError(
            "eligible must be a boolean",
            context={"reason": "invalid_governance_bundle"},
        )
    validate_probabilistic_promotion_decision(bundle.probabilistic)
    validate_conformal_governance_decision(bundle.conformal)
    validate_joint_probabilistic_governance_decision(bundle.joint)
    if bundle.joint.probabilistic_decision_fingerprint != bundle.probabilistic.fingerprint:
        raise StateSpaceError(
            "joint decision is not bound to bundled probabilistic evidence",
            context={"reason": "governance_bundle_identity_mismatch"},
        )
    if bundle.joint.conformal_decision_fingerprint != bundle.conformal.fingerprint:
        raise StateSpaceError(
            "joint decision is not bound to bundled conformal evidence",
            context={"reason": "governance_bundle_identity_mismatch"},
        )

    for name, value in (
        ("ensemble_targets", bundle.ensemble_targets),
        ("conformal_targets", bundle.conformal_targets),
        ("aligned_targets", bundle.aligned_targets),
    ):
        _positive_integer(name, value)
    if bundle.aligned_targets != bundle.conformal_targets:
        raise StateSpaceError(
            "all conformal targets must be aligned in a valid bundle",
            context={"reason": "invalid_governance_bundle"},
        )
    if bundle.aligned_targets > bundle.ensemble_targets:
        raise StateSpaceError(
            "aligned target count cannot exceed ensemble target count",
            context={"reason": "invalid_governance_bundle"},
        )
    expected_ratio = bundle.aligned_targets / bundle.ensemble_targets
    ratio = _open_closed_unit("aligned_target_ratio", bundle.aligned_target_ratio)
    if abs(ratio - expected_ratio) > 1e-12:
        raise StateSpaceError(
            "aligned target ratio disagrees with target counts",
            context={"reason": "invalid_governance_bundle"},
        )
    if (
        not isinstance(bundle.aligned_target_indices, tuple)
        or len(bundle.aligned_target_indices) != bundle.aligned_targets
        or any(
            isinstance(index, bool) or not isinstance(index, int) or index < 1
            for index in bundle.aligned_target_indices
        )
        or tuple(sorted(bundle.aligned_target_indices)) != bundle.aligned_target_indices
        or len(set(bundle.aligned_target_indices)) != len(bundle.aligned_target_indices)
    ):
        raise StateSpaceError(
            "aligned_target_indices must be unique, positive, and sorted",
            context={"reason": "invalid_governance_bundle"},
        )
    _validate_reasons(bundle.reasons, eligible=bundle.eligible)
    for name, value in (
        ("ensemble_target_fingerprint", bundle.ensemble_target_fingerprint),
        ("conformal_target_fingerprint", bundle.conformal_target_fingerprint),
        ("gate_fingerprint", bundle.gate_fingerprint),
        ("fingerprint", bundle.fingerprint),
    ):
        _validate_digest(name, value)

    expected = _bundle_fingerprint(
        eligible=bundle.eligible,
        reasons=bundle.reasons,
        probabilistic_fingerprint=bundle.probabilistic.fingerprint,
        conformal_fingerprint=bundle.conformal.fingerprint,
        joint_fingerprint=bundle.joint.fingerprint,
        ensemble_targets=bundle.ensemble_targets,
        conformal_targets=bundle.conformal_targets,
        aligned_targets=bundle.aligned_targets,
        aligned_target_ratio=bundle.aligned_target_ratio,
        aligned_target_indices=bundle.aligned_target_indices,
        ensemble_target_fingerprint=bundle.ensemble_target_fingerprint,
        conformal_target_fingerprint=bundle.conformal_target_fingerprint,
        gate_fingerprint=bundle.gate_fingerprint,
    )
    if bundle.fingerprint != expected:
        raise StateSpaceError(
            "probabilistic governance bundle fingerprint mismatch",
            context={"reason": "governance_bundle_identity_mismatch"},
        )


def _ensemble_target_pairs(
    ensemble: BayesianEnsembleReport,
) -> tuple[tuple[int, float], ...]:
    if not isinstance(ensemble, BayesianEnsembleReport) or not ensemble.steps:
        raise StateSpaceError(
            "ensemble report must contain steps",
            context={"reason": "invalid_governance_bundle_source"},
        )
    pairs = tuple((step.target_index, float(step.actual)) for step in ensemble.steps)
    return _validate_target_pairs(pairs, source="ensemble")


def _conformal_target_pairs(
    report: StratifiedConformalReport,
) -> tuple[tuple[int, float], ...]:
    if not isinstance(report, StratifiedConformalReport) or not report.steps:
        raise StateSpaceError(
            "conformal report must contain scored steps",
            context={"reason": "invalid_governance_bundle_source"},
        )
    pairs = tuple(
        (step.interval.target_index, float(step.actual))
        for step in report.steps
    )
    return _validate_target_pairs(pairs, source="conformal")


def _validate_target_pairs(
    pairs: tuple[tuple[int, float], ...],
    *,
    source: str,
) -> tuple[tuple[int, float], ...]:
    indices = tuple(index for index, _ in pairs)
    if len(set(indices)) != len(indices):
        raise StateSpaceError(
            f"{source} evidence contains duplicate target indices",
            context={"reason": "governance_target_alignment_mismatch"},
        )
    if tuple(sorted(indices)) != indices:
        raise StateSpaceError(
            f"{source} target indices must be strictly increasing",
            context={"reason": "governance_target_alignment_mismatch"},
        )
    for index, actual in pairs:
        if isinstance(index, bool) or not isinstance(index, int) or index < 1:
            raise StateSpaceError(
                f"{source} target index is invalid",
                context={"reason": "governance_target_alignment_mismatch"},
            )
        _finite(f"{source}_actual", actual)
    return pairs


def _validate_target_alignment(
    ensemble_pairs: tuple[tuple[int, float], ...],
    conformal_pairs: tuple[tuple[int, float], ...],
    *,
    max_actual_delta: float,
) -> tuple[int, ...]:
    ensemble_by_target = dict(ensemble_pairs)
    aligned: list[int] = []
    for target_index, actual in conformal_pairs:
        if target_index not in ensemble_by_target:
            raise StateSpaceError(
                "conformal evidence contains a target absent from ensemble evidence",
                context={
                    "reason": "governance_target_alignment_mismatch",
                    "target_index": target_index,
                },
            )
        source_actual = ensemble_by_target[target_index]
        if abs(source_actual - actual) > max_actual_delta:
            raise StateSpaceError(
                "evidence planes disagree on the realized target value",
                context={
                    "reason": "governance_target_alignment_mismatch",
                    "target_index": target_index,
                },
            )
        aligned.append(target_index)
    return tuple(aligned)


def _target_fingerprint(
    schema: str,
    pairs: tuple[tuple[int, float], ...],
) -> str:
    return _digest(
        {
            "schema": schema,
            "targets": [
                {"target_index": index, "actual": actual}
                for index, actual in pairs
            ],
        }
    )


def _gate_fingerprint(gate: ProbabilisticGovernanceBundleGate) -> str:
    return _digest(
        {
            "schema": "jeeves.probabilistic-governance-bundle-gate.v1",
            "min_aligned_target_ratio": gate.min_aligned_target_ratio,
            "max_actual_delta": gate.max_actual_delta,
        }
    )


def _bundle_fingerprint(
    *,
    eligible: bool,
    reasons: tuple[str, ...],
    probabilistic_fingerprint: str,
    conformal_fingerprint: str,
    joint_fingerprint: str,
    ensemble_targets: int,
    conformal_targets: int,
    aligned_targets: int,
    aligned_target_ratio: float,
    aligned_target_indices: tuple[int, ...],
    ensemble_target_fingerprint: str,
    conformal_target_fingerprint: str,
    gate_fingerprint: str,
) -> str:
    return _digest(
        {
            "schema": "jeeves.probabilistic-governance-bundle.v1",
            "eligible": eligible,
            "reasons": list(reasons),
            "probabilistic_fingerprint": probabilistic_fingerprint,
            "conformal_fingerprint": conformal_fingerprint,
            "joint_fingerprint": joint_fingerprint,
            "ensemble_targets": ensemble_targets,
            "conformal_targets": conformal_targets,
            "aligned_targets": aligned_targets,
            "aligned_target_ratio": aligned_target_ratio,
            "aligned_target_indices": list(aligned_target_indices),
            "ensemble_target_fingerprint": ensemble_target_fingerprint,
            "conformal_target_fingerprint": conformal_target_fingerprint,
            "gate_fingerprint": gate_fingerprint,
        }
    )


def _validate_reasons(reasons: tuple[str, ...], *, eligible: bool) -> None:
    if not isinstance(reasons, tuple) or not reasons:
        raise StateSpaceError(
            "reasons must be a non-empty tuple",
            context={"reason": "invalid_governance_bundle"},
        )
    if any(not isinstance(reason, str) or not reason for reason in reasons):
        raise StateSpaceError(
            "reasons must contain non-empty strings",
            context={"reason": "invalid_governance_bundle"},
        )
    passed = "probabilistic_governance_bundle_passed" in reasons
    if eligible != passed or (passed and len(reasons) != 1):
        raise StateSpaceError(
            "bundle reasons disagree with eligibility",
            context={"reason": "invalid_governance_bundle"},
        )


def _validate_digest(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise StateSpaceError(
            f"{name} must be a sha256 hex digest",
            context={"reason": "invalid_governance_bundle"},
        )


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StateSpaceError(
            f"{name} must be numeric",
            context={"reason": "invalid_governance_bundle_gate", "field": name},
        )
    number = float(value)
    if not math.isfinite(number):
        raise StateSpaceError(
            f"{name} must be finite",
            context={"reason": "invalid_governance_bundle_gate", "field": name},
        )
    return number


def _open_closed_unit(name: str, value: object) -> float:
    number = _finite(name, value)
    if not 0.0 < number <= 1.0:
        raise StateSpaceError(
            f"{name} must lie in (0, 1]",
            context={"reason": "invalid_governance_bundle_gate", "field": name},
        )
    return number


def _positive_integer(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise StateSpaceError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_governance_bundle", "field": name},
        )
    return value


__all__ = [
    "ProbabilisticGovernanceBundle",
    "ProbabilisticGovernanceBundleGate",
    "evaluate_probabilistic_governance_bundle",
    "validate_probabilistic_governance_bundle",
]
