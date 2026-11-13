"""Rollback planning from release history and health verdicts."""

from __future__ import annotations

from dataclasses import dataclass
import math

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.health_check import HealthReport, VERDICTS
from skeleton.build.delivery.release_history import ReleaseHistory, ReleaseRecord

TRIGGERS = frozenset({"health", "manual", "error-budget", "promotion-veto"})


@dataclass(frozen=True)
class RollbackDecision:
    should_rollback: bool
    reason: str
    target: ReleaseRecord | None


@dataclass(frozen=True)
class RollbackPlan:
    environment: str
    from_release: str
    to_release: str
    to_manifest_digest: str
    to_config_digest: str
    trigger: str
    steps: tuple[str, ...]


def decide(
    report: HealthReport,
    *,
    error_rate: float = 0.0,
    error_budget: float = 0.01,
    tolerate_degraded: bool = True,
) -> RollbackDecision:
    if (not isinstance(report, HealthReport)
            or type(report.verdict) is not str or report.verdict not in VERDICTS
            or type(report.failing_probes) is not tuple
            or (report.verdict == "healthy" and bool(report.failing_probes))):
        raise DeliveryError("invalid or contradictory health report evidence")
    if (type(error_rate) not in (int, float) or type(error_budget) not in (int, float)
            or not math.isfinite(error_rate) or not math.isfinite(error_budget)
            or not 0 <= error_rate <= 1 or not 0 < error_budget <= 1):
        raise DeliveryError("error rates must be fractions")
    if type(tolerate_degraded) is not bool:
        raise DeliveryError("tolerate_degraded must be a boolean")
    if report.verdict == "unhealthy":
        return RollbackDecision(True, "health:" + ",".join(report.failing_probes), None)
    if report.verdict == "degraded" and not tolerate_degraded:
        return RollbackDecision(True, "degraded", None)
    if error_rate > error_budget:
        return RollbackDecision(True, f"error-budget:{error_rate:.4f}>{error_budget:.4f}", None)
    return RollbackDecision(False, "within-budget", None)


def plan_rollback(history: ReleaseHistory, *, trigger: str) -> RollbackPlan:
    if type(trigger) is not str or trigger not in TRIGGERS:
        raise DeliveryError(f"unknown rollback trigger {trigger!r}")
    current = history.current()
    if current is None:
        raise DeliveryError("nothing deployed; cannot roll back")
    target = history.last_known_good(exclude_release=current.release_id)
    if target is None:
        raise DeliveryError("no known-good release to roll back to")
    steps = (
        f"freeze:{history.environment}",
        f"fetch-manifest:{target.manifest_digest}",
        f"verify-manifest:{target.manifest_digest}",
        f"apply-config:{target.config_digest}",
        f"switch-traffic:{current.release_id}->{target.release_id}",
        "health-gate",
        f"record:rolled-back:{target.release_id}",
        f"unfreeze:{history.environment}",
    )
    return RollbackPlan(
        history.environment, current.release_id, target.release_id,
        target.manifest_digest, target.config_digest, trigger, steps,
    )
