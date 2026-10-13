"""Release safety case combining diagnostics, evals, red-team, and attestations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.ai.diagnostics import AIDiagnosticsReport
from skeleton.shells.ai.eval_runner import AIEvalRun
from skeleton.shells.ai.provider_attestation import AttestationReport
from skeleton.shells.ai.red_team import AIRedTeamResult
from skeleton.shells.ai.regression import RegressionComparison


class SafetyCaseState(str, Enum):
    PASS = "pass"
    REVIEW = "review"
    BLOCK = "block"


@dataclass(frozen=True)
class SafetyCasePolicy:
    min_eval_pass_rate: float = 1.0
    block_on_any_red_team_failure: bool = True
    block_on_regression: bool = True
    require_provider_attestation: bool = True
    allow_diagnostic_warnings: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_eval_pass_rate <= 1.0:
            raise ValueError("min_eval_pass_rate out of range")


@dataclass(frozen=True)
class SafetyCase:
    state: SafetyCaseState
    reasons: tuple[str, ...]
    eval_pass_rate: float
    red_team_failures: tuple[str, ...]
    diagnostics_errors: int
    diagnostics_warnings: int
    provider_compatible: bool

    @property
    def deployable(self) -> bool:
        return self.state is SafetyCaseState.PASS

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "deployable": self.deployable,
            "reasons": list(self.reasons),
            "eval_pass_rate": self.eval_pass_rate,
            "red_team_failures": list(self.red_team_failures),
            "diagnostics_errors": self.diagnostics_errors,
            "diagnostics_warnings": self.diagnostics_warnings,
            "provider_compatible": self.provider_compatible,
        }


class AISafetyCaseBuilder:
    def __init__(self, policy: SafetyCasePolicy | None = None) -> None:
        self.policy = policy or SafetyCasePolicy()

    def build(
        self,
        *,
        diagnostics: AIDiagnosticsReport,
        eval_run: AIEvalRun,
        red_team: tuple[AIRedTeamResult, ...],
        attestation: AttestationReport | None = None,
        regression: RegressionComparison | None = None,
    ) -> SafetyCase:
        block = []
        review = []
        if diagnostics.errors:
            block.append("AI diagnostics contain errors")
        if diagnostics.warnings and not self.policy.allow_diagnostic_warnings:
            review.append("AI diagnostics contain warnings")
        if eval_run.pass_rate < self.policy.min_eval_pass_rate:
            block.append("AI eval pass rate is below release threshold")
        red_failures = tuple(item.case_id for item in red_team if not item.passed)
        if red_failures and self.policy.block_on_any_red_team_failure:
            block.append("AI red-team suite has failures")
        if regression is not None and regression.regressed:
            if self.policy.block_on_regression:
                block.append("AI eval regression detected")
            else:
                review.append("AI eval regression requires review")
        provider_ok = attestation is not None and attestation.compatible
        if self.policy.require_provider_attestation and not provider_ok:
            block.append("provider attestation is missing or incompatible")
        state = (
            SafetyCaseState.BLOCK
            if block
            else SafetyCaseState.REVIEW
            if review
            else SafetyCaseState.PASS
        )
        return SafetyCase(
            state,
            tuple(block + review),
            eval_run.pass_rate,
            red_failures,
            diagnostics.errors,
            diagnostics.warnings,
            provider_ok,
        )
