"""Stable-root deployment preflight for ProductControlPlane-like objects.

A deployment decision is meaningless if governed state mutates while the gate is
being evaluated. The coordinator samples the whole-system root before and after
assurance/trust evaluation, retries boundedly, and only authorizes a report produced
against a stable canonical SHA-256 root.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hmac
import re
from typing import Any, Mapping

from core.canonical_json import CanonicalJSONError, canonical_json_sha256
from core.deployment_preflight import (
    DeploymentPreflight,
    evaluate_deployment_preflight,
    verify_deployment_preflight,
)

CONTROL_PLANE_PREFLIGHT_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


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


def _sha(value: Any) -> str:
    return canonical_json_sha256(value)


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("evaluated_at must be a timezone-aware timestamp string")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("evaluated_at must be timezone-aware")
    return value


def _root(plane: Any) -> str:
    raw = plane.system_root()
    if not isinstance(raw, Mapping):
        return ""
    value = raw.get("root_sha256")
    return value if isinstance(value, str) else ""


def _payload(
    *,
    allowed: bool,
    stable: bool,
    attempts: int,
    root_before_sha256: str,
    root_after_sha256: str,
    evaluated_at: str,
    unstable_reason: str,
    report: DeploymentPreflight,
) -> dict[str, Any]:
    return {
        "version": CONTROL_PLANE_PREFLIGHT_VERSION,
        "allowed": allowed,
        "stable": stable,
        "attempts": attempts,
        "root_before_sha256": root_before_sha256,
        "root_after_sha256": root_after_sha256,
        "evaluated_at": evaluated_at,
        "unstable_reason": unstable_reason,
        "report": asdict(report),
    }


def _build(
    *,
    allowed: bool,
    stable: bool,
    attempts: int,
    root_before_sha256: str,
    root_after_sha256: str,
    evaluated_at: str,
    unstable_reason: str,
    report: DeploymentPreflight,
) -> ControlPlaneDeploymentPreflight:
    payload = _payload(
        allowed=allowed,
        stable=stable,
        attempts=attempts,
        root_before_sha256=root_before_sha256,
        root_after_sha256=root_after_sha256,
        evaluated_at=evaluated_at,
        unstable_reason=unstable_reason,
        report=report,
    )
    return ControlPlaneDeploymentPreflight(
        CONTROL_PLANE_PREFLIGHT_VERSION,
        allowed,
        stable,
        attempts,
        root_before_sha256,
        root_after_sha256,
        evaluated_at,
        unstable_reason,
        report,
        _sha(payload),
    )


def evaluate_control_plane_deployment(
    plane: Any,
    *,
    max_attempts: int = 3,
    evaluated_at: str | None = None,
) -> ControlPlaneDeploymentPreflight:
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1 or max_attempts > 10:
        raise ValueError("max_attempts must be an integer between 1 and 10")
    stamp = _timestamp(evaluated_at) if evaluated_at is not None else datetime.now(UTC).isoformat()

    last_before = ""
    last_after = ""
    last_report: DeploymentPreflight | None = None
    saw_invalid_root = False

    for attempt in range(1, max_attempts + 1):
        before = _root(plane)
        assurance = plane.assurance_report()
        trust = plane.epistemic_finality()
        after = _root(plane)
        last_before, last_after = before, after
        roots_valid = _is_sha(before) and _is_sha(after)
        saw_invalid_root = saw_invalid_root or not roots_valid
        last_report = evaluate_deployment_preflight(
            assurance=assurance,
            trust=trust,
            system_root_sha256=after,
        )
        if roots_valid and before == after:
            return _build(
                allowed=last_report.allowed,
                stable=True,
                attempts=attempt,
                root_before_sha256=before,
                root_after_sha256=after,
                evaluated_at=stamp,
                unstable_reason="",
                report=last_report,
            )

    assert last_report is not None
    if saw_invalid_root:
        reason = f"whole-system root was invalid or unstable during {max_attempts} consecutive preflight attempt(s)"
    else:
        reason = f"whole-system root changed during {max_attempts} consecutive preflight attempt(s)"
    return _build(
        allowed=False,
        stable=False,
        attempts=max_attempts,
        root_before_sha256=last_before,
        root_after_sha256=last_after,
        evaluated_at=stamp,
        unstable_reason=reason,
        report=last_report,
    )


def verify_control_plane_deployment_preflight(report: ControlPlaneDeploymentPreflight) -> bool:
    try:
        if not isinstance(report, ControlPlaneDeploymentPreflight):
            return False
        if isinstance(report.version, bool) or report.version != CONTROL_PLANE_PREFLIGHT_VERSION:
            return False
        if not isinstance(report.allowed, bool) or not isinstance(report.stable, bool):
            return False
        if isinstance(report.attempts, bool) or not isinstance(report.attempts, int) or not 1 <= report.attempts <= 10:
            return False
        _timestamp(report.evaluated_at)
        if not verify_deployment_preflight(report.report):
            return False
        if not _is_sha(report.root_before_sha256) or not _is_sha(report.root_after_sha256):
            return False
        if report.report.system_root_sha256 != report.root_after_sha256:
            return False
        if report.stable:
            if report.root_before_sha256 != report.root_after_sha256 or report.unstable_reason:
                return False
            if report.allowed != report.report.allowed:
                return False
        else:
            if report.allowed or not isinstance(report.unstable_reason, str) or not report.unstable_reason:
                return False
        payload = _payload(
            allowed=report.allowed,
            stable=report.stable,
            attempts=report.attempts,
            root_before_sha256=report.root_before_sha256,
            root_after_sha256=report.root_after_sha256,
            evaluated_at=report.evaluated_at,
            unstable_reason=report.unstable_reason,
            report=report.report,
        )
        return hmac.compare_digest(_sha(payload), report.attestation_sha256)
    except (CanonicalJSONError, TypeError, ValueError):
        return False


def control_plane_preflight_dict(plane: Any, *, max_attempts: int = 3) -> dict[str, Any]:
    report = evaluate_control_plane_deployment(plane, max_attempts=max_attempts)
    payload = asdict(report)
    payload["self_verified"] = verify_control_plane_deployment_preflight(report)
    return payload
