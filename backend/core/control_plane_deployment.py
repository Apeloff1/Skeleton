"""Stable-root deployment preflight for ProductControlPlane-like objects.

A deployment decision is meaningless if the governed state mutates while the gate is
being evaluated. This coordinator samples the whole-system root before and after
assurance/trust evaluation, retries boundedly, and only authorizes a report produced
against a stable root. It does not lock the entire product runtime; instead it makes
concurrent mutation explicit and fail-closed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
from typing import Any

from core.deployment_preflight import DeploymentPreflight, evaluate_deployment_preflight, verify_deployment_preflight

CONTROL_PLANE_PREFLIGHT_VERSION = 1


@dataclass(frozen=True, slots=True)
class ControlPlaneDeploymentPreflight:
    version: int
    allowed: bool
    stable: bool
    attempts: int
    root_before_sha256: str
    root_after_sha256: str
    evaluated_at: str
    unstable_reason: str
    report: DeploymentPreflight
    attestation_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _payload(*, allowed: bool, stable: bool, attempts: int, root_before_sha256: str,
             root_after_sha256: str, evaluated_at: str, unstable_reason: str,
             report: DeploymentPreflight) -> dict[str, Any]:
    return {
        "version": CONTROL_PLANE_PREFLIGHT_VERSION,
        "allowed": allowed, "stable": stable, "attempts": attempts,
        "root_before_sha256": root_before_sha256, "root_after_sha256": root_after_sha256,
        "evaluated_at": evaluated_at, "unstable_reason": unstable_reason,
        "report": asdict(report),
    }


def evaluate_control_plane_deployment(plane, *, max_attempts: int = 3,
                                      evaluated_at: str | None = None) -> ControlPlaneDeploymentPreflight:
    if max_attempts < 1 or max_attempts > 10:
        raise ValueError("max_attempts must be between 1 and 10")
    stamp = evaluated_at or datetime.now(UTC).isoformat()
    last_before = ""; last_after = ""; last_report: DeploymentPreflight | None = None
    for attempt in range(1, max_attempts + 1):
        before = str(plane.system_root()["root_sha256"])
        assurance = plane.assurance_report()
        trust = plane.epistemic_finality()
        after = str(plane.system_root()["root_sha256"])
        last_before, last_after = before, after
        last_report = evaluate_deployment_preflight(
            assurance=assurance, trust=trust, system_root_sha256=after,
        )
        if before == after:
            payload = _payload(
                allowed=last_report.allowed, stable=True, attempts=attempt,
                root_before_sha256=before, root_after_sha256=after,
                evaluated_at=stamp, unstable_reason="", report=last_report,
            )
            return ControlPlaneDeploymentPreflight(**payload, attestation_sha256=_sha(payload))
    assert last_report is not None
    reason = f"whole-system root changed during {max_attempts} consecutive preflight attempt(s)"
    payload = _payload(
        allowed=False, stable=False, attempts=max_attempts,
        root_before_sha256=last_before, root_after_sha256=last_after,
        evaluated_at=stamp, unstable_reason=reason, report=last_report,
    )
    return ControlPlaneDeploymentPreflight(**payload, attestation_sha256=_sha(payload))


def verify_control_plane_deployment_preflight(report: ControlPlaneDeploymentPreflight) -> bool:
    if report.version != CONTROL_PLANE_PREFLIGHT_VERSION or not verify_deployment_preflight(report.report):
        return False
    if report.allowed and (not report.stable or not report.report.allowed):
        return False
    if report.stable and report.root_before_sha256 != report.root_after_sha256:
        return False
    if not report.stable and not report.unstable_reason:
        return False
    payload = _payload(
        allowed=report.allowed, stable=report.stable, attempts=report.attempts,
        root_before_sha256=report.root_before_sha256, root_after_sha256=report.root_after_sha256,
        evaluated_at=report.evaluated_at, unstable_reason=report.unstable_reason, report=report.report,
    )
    return hmac.compare_digest(_sha(payload), report.attestation_sha256)


def control_plane_preflight_dict(plane, *, max_attempts: int = 3) -> dict[str, Any]:
    report = evaluate_control_plane_deployment(plane, max_attempts=max_attempts)
    payload = asdict(report)
    payload["self_verified"] = verify_control_plane_deployment_preflight(report)
    return payload
