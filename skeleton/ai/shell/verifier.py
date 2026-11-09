"""Post-execution verification against explicit user-visible criteria."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.ai.types import AIIntent, VerificationCriterion
from skeleton.shells.plan_executor import PlanExecutionReport


class VerificationState(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_OBSERVED = "not_observed"


@dataclass(frozen=True)
class CriterionResult:
    criterion_id: str
    state: VerificationState
    message: str
    required: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "criterion_id": self.criterion_id,
            "state": self.state.value,
            "message": self.message,
            "required": self.required,
        }


@dataclass(frozen=True)
class VerificationReport:
    criteria: tuple[CriterionResult, ...]

    @property
    def verified(self) -> bool:
        return all(
            item.state is VerificationState.PASSED
            for item in self.criteria
            if item.required
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "verified": self.verified,
            "criteria": [item.to_dict() for item in self.criteria],
        }


class PlanVerifier:
    """Verify criteria from receipt metadata and plan outcomes.

    Criteria do not execute extra commands here. A separate verification plan may
    be proposed if active checking is required.
    """

    def verify(
        self,
        intent: AIIntent,
        report: PlanExecutionReport,
    ) -> VerificationReport:
        by_command: dict[str, list] = {}
        for step in report.steps:
            if step.dispatch is None:
                continue
            receipt = step.dispatch.outcome.final_receipt
            by_command.setdefault(receipt.command, []).append(receipt)

        results = []
        for criterion in intent.success_criteria:
            results.append(self._criterion(criterion, by_command))
        if not intent.success_criteria:
            results.append(
                CriterionResult(
                    "plan_execution",
                    VerificationState.PASSED if report.ok else VerificationState.FAILED,
                    "plan completed successfully" if report.ok else "plan reported failure",
                    True,
                )
            )
        return VerificationReport(tuple(results))

    @staticmethod
    def _criterion(
        criterion: VerificationCriterion,
        by_command: dict[str, list],
    ) -> CriterionResult:
        if not criterion.command:
            return CriterionResult(
                criterion.criterion_id,
                VerificationState.NOT_OBSERVED,
                "criterion has no passive command observation binding",
                criterion.required,
            )
        receipts = by_command.get(criterion.command, [])
        if not receipts:
            return CriterionResult(
                criterion.criterion_id,
                VerificationState.NOT_OBSERVED,
                "criterion command was not observed",
                criterion.required,
            )
        passed = any(
            receipt.returncode in criterion.expected_returncodes
            and receipt.ok
            for receipt in receipts
        )
        return CriterionResult(
            criterion.criterion_id,
            VerificationState.PASSED if passed else VerificationState.FAILED,
            "matching successful receipt observed" if passed else "no matching successful receipt observed",
            criterion.required,
        )
