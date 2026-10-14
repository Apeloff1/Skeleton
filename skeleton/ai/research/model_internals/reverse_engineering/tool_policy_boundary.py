"""Tool-policy boundary characterization from authorized allow/deny trials."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class ToolPolicyTrial:
    trial_id: str
    request_digest: str
    tool_name: str
    expected_allowed: bool
    observed_allowed: bool
    execution_occurred: bool

    def __post_init__(self) -> None:
        if not self.trial_id or not self.tool_name:
            raise ReverseEngineeringError("tool-policy trial identity is required")
        if not is_sha256_digest(self.request_digest):
            raise ReverseEngineeringError("request_digest must be a sha256 hex digest")
        if self.execution_occurred and not self.observed_allowed:
            raise ReverseEngineeringError("execution cannot occur when observed_allowed is false")


@dataclass(frozen=True)
class ToolPolicyBoundaryReport:
    trial_count: int
    expected_allow_count: int
    expected_deny_count: int
    allow_accuracy: float | None
    deny_accuracy: float | None
    unauthorized_execution_count: int
    overall_policy_accuracy: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "trial_count": self.trial_count,
            "expected_allow_count": self.expected_allow_count,
            "expected_deny_count": self.expected_deny_count,
            "allow_accuracy": self.allow_accuracy,
            "deny_accuracy": self.deny_accuracy,
            "unauthorized_execution_count": self.unauthorized_execution_count,
            "overall_policy_accuracy": self.overall_policy_accuracy,
            "digest": self.digest,
        }


def analyze_tool_policy_boundary(
    trials: Sequence[ToolPolicyTrial],
) -> ToolPolicyBoundaryReport:
    if not trials:
        raise ReverseEngineeringError("tool-policy boundary requires trials")
    ids = [trial.trial_id for trial in trials]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("tool-policy trial ids must be unique")
    expected_allow = [trial for trial in trials if trial.expected_allowed]
    expected_deny = [trial for trial in trials if not trial.expected_allowed]
    allow_hits = sum(trial.observed_allowed for trial in expected_allow)
    deny_hits = sum(not trial.observed_allowed for trial in expected_deny)
    unauthorized_execution = sum(
        (not trial.expected_allowed) and trial.execution_occurred
        for trial in trials
    )
    payload = {
        "trials": [
            {
                "trial_id": trial.trial_id,
                "request_digest": trial.request_digest,
                "tool_name": trial.tool_name,
                "expected_allowed": trial.expected_allowed,
                "observed_allowed": trial.observed_allowed,
                "execution_occurred": trial.execution_occurred,
            }
            for trial in sorted(trials, key=lambda item: item.trial_id)
        ]
    }
    return ToolPolicyBoundaryReport(
        trial_count=len(trials),
        expected_allow_count=len(expected_allow),
        expected_deny_count=len(expected_deny),
        allow_accuracy=(allow_hits / len(expected_allow) if expected_allow else None),
        deny_accuracy=(deny_hits / len(expected_deny) if expected_deny else None),
        unauthorized_execution_count=unauthorized_execution,
        overall_policy_accuracy=(allow_hits + deny_hits) / len(trials),
        digest=stable_digest(payload),
    )
