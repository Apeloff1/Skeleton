"""Cross-evidence assurance gate for Jeeves historical model decisions.

Individual historical subsystems answer different questions:

* backtesting measures forward selection regret and stability,
* calibration measures whether score magnitude predicts later outcomes,
* sensitivity measures whether the champion survives reasonable policy shifts,
* lineage drift measures whether a generation upgrade hides domain regressions.

This module combines those *already-computed* reports into one deterministic,
auditable assurance envelope. It never invents missing evidence and never mutates
model state. Missing required evidence fails closed according to policy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from skeleton.jeeves.historical_backtest import BacktestReport
from skeleton.jeeves.historical_calibration import CalibrationReport
from skeleton.jeeves.historical_lineage import GenerationDriftReport
from skeleton.jeeves.historical_models import ModelIdentity, canonical_fingerprint
from skeleton.jeeves.historical_sensitivity import SelectionSensitivityReport


class HistoricalAssuranceError(ValueError):
    """Invalid assurance policy or evidence bundle."""


def _unit(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalAssuranceError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise HistoricalAssuranceError(f"{name} must be finite and between 0 and 1")
    return number


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalAssuranceError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class AssurancePolicy:
    min_backtest_folds: int = 3
    max_mean_regret: float = 0.03
    max_worst_regret: float = 0.08
    min_champion_stability: float = 0.50
    max_calibration_mae: float = 0.08
    max_calibration_rmse: float = 0.10
    min_calibration_samples: int = 3
    min_sensitivity_champion_share: float = 0.80
    max_sensitivity_regret: float = 0.03
    require_sensitivity_robust: bool = True
    require_no_structural_drift: bool = True
    require_drift_report_for_upgrade: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "min_backtest_folds", _positive_int("min_backtest_folds", self.min_backtest_folds))
        object.__setattr__(
            self,
            "min_calibration_samples",
            _positive_int("min_calibration_samples", self.min_calibration_samples),
        )
        for name in (
            "max_mean_regret",
            "max_worst_regret",
            "min_champion_stability",
            "max_calibration_mae",
            "max_calibration_rmse",
            "min_sensitivity_champion_share",
            "max_sensitivity_regret",
        ):
            object.__setattr__(self, name, _unit(name, getattr(self, name)))
        for name in (
            "require_sensitivity_robust",
            "require_no_structural_drift",
            "require_drift_report_for_upgrade",
        ):
            if not isinstance(getattr(self, name), bool):
                raise HistoricalAssuranceError(f"{name} must be boolean")
        if self.max_worst_regret < self.max_mean_regret:
            raise HistoricalAssuranceError("max_worst_regret must be >= max_mean_regret")
        if self.max_calibration_rmse < self.max_calibration_mae:
            raise HistoricalAssuranceError("max_calibration_rmse must be >= max_calibration_mae")

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "min_backtest_folds": self.min_backtest_folds,
                "max_mean_regret": self.max_mean_regret,
                "max_worst_regret": self.max_worst_regret,
                "min_champion_stability": self.min_champion_stability,
                "max_calibration_mae": self.max_calibration_mae,
                "max_calibration_rmse": self.max_calibration_rmse,
                "min_calibration_samples": self.min_calibration_samples,
                "min_sensitivity_champion_share": self.min_sensitivity_champion_share,
                "max_sensitivity_regret": self.max_sensitivity_regret,
                "require_sensitivity_robust": self.require_sensitivity_robust,
                "require_no_structural_drift": self.require_no_structural_drift,
                "require_drift_report_for_upgrade": self.require_drift_report_for_upgrade,
            }
        )


@dataclass(frozen=True, slots=True)
class AssuranceEvidence:
    candidate: ModelIdentity
    backtest: BacktestReport
    calibration: CalibrationReport
    sensitivity: SelectionSensitivityReport
    drift: GenerationDriftReport | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, ModelIdentity):
            raise HistoricalAssuranceError("candidate must be ModelIdentity")
        if not isinstance(self.backtest, BacktestReport):
            raise HistoricalAssuranceError("backtest must be BacktestReport")
        if not isinstance(self.calibration, CalibrationReport):
            raise HistoricalAssuranceError("calibration must be CalibrationReport")
        if not isinstance(self.sensitivity, SelectionSensitivityReport):
            raise HistoricalAssuranceError("sensitivity must be SelectionSensitivityReport")
        if self.drift is not None and not isinstance(self.drift, GenerationDriftReport):
            raise HistoricalAssuranceError("drift must be GenerationDriftReport or None")
        if self.sensitivity.base_champion != self.candidate:
            raise HistoricalAssuranceError("sensitivity base champion must match assurance candidate")
        selected = {fold.selected_model for fold in self.backtest.folds}
        if self.candidate not in selected:
            raise HistoricalAssuranceError("candidate must appear in backtest selections")
        if self.drift is not None and self.drift.child != self.candidate:
            raise HistoricalAssuranceError("drift child must match assurance candidate")


@dataclass(frozen=True, slots=True)
class AssuranceCheck:
    check_id: str
    passed: bool
    observed: float | int | bool | str | None
    required: float | int | bool | str | None
    evidence_fingerprint: str


@dataclass(frozen=True, slots=True)
class HistoricalAssuranceReport:
    candidate: ModelIdentity
    passed: bool
    checks: tuple[AssuranceCheck, ...]
    reasons: tuple[str, ...]
    policy_fingerprint: str
    backtest_fingerprint: str
    calibration_fingerprint: str
    sensitivity_fingerprint: str
    drift_fingerprint: str | None
    report_fingerprint: str

    @property
    def passed_count(self) -> int:
        return sum(1 for check in self.checks if check.passed)

    @property
    def failed_count(self) -> int:
        return len(self.checks) - self.passed_count


class HistoricalAssuranceGate:
    """Combine independent historical diagnostics into one readiness report."""

    def __init__(self, policy: AssurancePolicy | None = None) -> None:
        self.policy = policy or AssurancePolicy()
        if not isinstance(self.policy, AssurancePolicy):
            raise HistoricalAssuranceError("policy must be AssurancePolicy")

    def evaluate(self, evidence: AssuranceEvidence) -> HistoricalAssuranceReport:
        if not isinstance(evidence, AssuranceEvidence):
            raise HistoricalAssuranceError("evidence must be AssuranceEvidence")
        checks: list[AssuranceCheck] = []
        backtest_fp = evidence.backtest.report_fingerprint
        calibration_fp = evidence.calibration.report_fingerprint
        sensitivity_fp = evidence.sensitivity.report_fingerprint
        drift_fp = evidence.drift.report_fingerprint if evidence.drift is not None else None

        self._append(
            checks,
            "backtest_min_folds",
            evidence.backtest.fold_count >= self.policy.min_backtest_folds,
            evidence.backtest.fold_count,
            self.policy.min_backtest_folds,
            backtest_fp,
        )
        self._append(
            checks,
            "backtest_mean_regret",
            evidence.backtest.mean_regret <= self.policy.max_mean_regret + 1e-12,
            evidence.backtest.mean_regret,
            self.policy.max_mean_regret,
            backtest_fp,
        )
        self._append(
            checks,
            "backtest_worst_regret",
            evidence.backtest.worst_regret <= self.policy.max_worst_regret + 1e-12,
            evidence.backtest.worst_regret,
            self.policy.max_worst_regret,
            backtest_fp,
        )
        self._append(
            checks,
            "backtest_champion_stability",
            evidence.backtest.champion_stability + 1e-12 >= self.policy.min_champion_stability,
            evidence.backtest.champion_stability,
            self.policy.min_champion_stability,
            backtest_fp,
        )
        self._append(
            checks,
            "calibration_min_samples",
            evidence.calibration.sample_count >= self.policy.min_calibration_samples,
            evidence.calibration.sample_count,
            self.policy.min_calibration_samples,
            calibration_fp,
        )
        self._append(
            checks,
            "calibration_mae",
            evidence.calibration.mean_absolute_error <= self.policy.max_calibration_mae + 1e-12,
            evidence.calibration.mean_absolute_error,
            self.policy.max_calibration_mae,
            calibration_fp,
        )
        self._append(
            checks,
            "calibration_rmse",
            evidence.calibration.root_mean_squared_error <= self.policy.max_calibration_rmse + 1e-12,
            evidence.calibration.root_mean_squared_error,
            self.policy.max_calibration_rmse,
            calibration_fp,
        )
        self._append(
            checks,
            "sensitivity_champion_share",
            evidence.sensitivity.champion_share + 1e-12 >= self.policy.min_sensitivity_champion_share,
            evidence.sensitivity.champion_share,
            self.policy.min_sensitivity_champion_share,
            sensitivity_fp,
        )
        self._append(
            checks,
            "sensitivity_regret",
            evidence.sensitivity.max_base_champion_regret <= self.policy.max_sensitivity_regret + 1e-12,
            evidence.sensitivity.max_base_champion_regret,
            self.policy.max_sensitivity_regret,
            sensitivity_fp,
        )
        if self.policy.require_sensitivity_robust:
            self._append(
                checks,
                "sensitivity_robust",
                evidence.sensitivity.robust,
                evidence.sensitivity.robust,
                True,
                sensitivity_fp,
            )
        if evidence.drift is not None:
            if self.policy.require_no_structural_drift:
                self._append(
                    checks,
                    "lineage_no_structural_break",
                    not evidence.drift.structural_break,
                    evidence.drift.structural_break,
                    False,
                    drift_fp or "",
                )
        elif self.policy.require_drift_report_for_upgrade:
            self._append(
                checks,
                "lineage_drift_report_present",
                False,
                None,
                "required",
                "missing",
            )

        reasons = tuple(check.check_id for check in checks if not check.passed)
        passed = not reasons
        payload = {
            "candidate": evidence.candidate.key,
            "policy": self.policy.fingerprint,
            "backtest": backtest_fp,
            "calibration": calibration_fp,
            "sensitivity": sensitivity_fp,
            "drift": drift_fp,
            "checks": [
                {
                    "id": check.check_id,
                    "passed": check.passed,
                    "observed": check.observed,
                    "required": check.required,
                    "evidence": check.evidence_fingerprint,
                }
                for check in checks
            ],
        }
        return HistoricalAssuranceReport(
            candidate=evidence.candidate,
            passed=passed,
            checks=tuple(checks),
            reasons=reasons,
            policy_fingerprint=self.policy.fingerprint,
            backtest_fingerprint=backtest_fp,
            calibration_fingerprint=calibration_fp,
            sensitivity_fingerprint=sensitivity_fp,
            drift_fingerprint=drift_fp,
            report_fingerprint=canonical_fingerprint(payload),
        )

    @staticmethod
    def _append(
        checks: list[AssuranceCheck],
        check_id: str,
        passed: bool,
        observed: float | int | bool | str | None,
        required: float | int | bool | str | None,
        evidence_fingerprint: str,
    ) -> None:
        checks.append(
            AssuranceCheck(
                check_id=check_id,
                passed=bool(passed),
                observed=observed,
                required=required,
                evidence_fingerprint=evidence_fingerprint,
            )
        )


def summarize_assurance(report: HistoricalAssuranceReport) -> dict[str, object]:
    return {
        "candidate": report.candidate.key,
        "passed": report.passed,
        "passed_count": report.passed_count,
        "failed_count": report.failed_count,
        "reasons": list(report.reasons),
        "policy_fingerprint": report.policy_fingerprint,
        "backtest_fingerprint": report.backtest_fingerprint,
        "calibration_fingerprint": report.calibration_fingerprint,
        "sensitivity_fingerprint": report.sensitivity_fingerprint,
        "drift_fingerprint": report.drift_fingerprint,
        "report_fingerprint": report.report_fingerprint,
        "checks": [
            {
                "check_id": check.check_id,
                "passed": check.passed,
                "observed": check.observed,
                "required": check.required,
                "evidence_fingerprint": check.evidence_fingerprint,
            }
            for check in report.checks
        ],
    }