"""Lifecycle evidence for high-risk AI sandbox execution.

The existing sandbox compiler proves requested isolation and backend capability.
This contract proves the lifecycle facts that must also hold around an actual
execution: the work runs outside the control-plane process, receives no ambient
credentials, gets only expiring secret references, bounds output, scans emitted
artifacts, and verifies cleanup of its ephemeral work directory.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Iterable


class SandboxLifecycleError(RuntimeError):
    """Sandbox lifecycle evidence is malformed or fails a required invariant."""


_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,255}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_MODES = frozenset({"container", "namespace", "sandboxed-subprocess"})
_ALLOWED_CHILD_POLICIES = frozenset({"deny", "scoped"})


def _text(name: str, value: object, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SandboxLifecycleError(f"{name} must be non-empty text")
    result = value.strip()
    if result != value or len(result) > maximum:
        raise SandboxLifecycleError(f"{name} must be normalized bounded text")
    return result


def _token(name: str, value: object) -> str:
    result = _text(name, value)
    if _TOKEN.fullmatch(result) is None:
        raise SandboxLifecycleError(f"{name} is not a canonical token")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if _SHA.fullmatch(result) is None:
        raise SandboxLifecycleError(f"{name} must be lowercase sha256")
    return result


def _time(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SandboxLifecycleError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise SandboxLifecycleError(f"{name} must be finite and non-negative")
    return result


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SandboxLifecycleError("lifecycle evidence must be canonical JSON") from exc
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class SecretProjectionEvidence:
    """Reference-only secret projection; never stores a secret value."""

    secret_ref: str
    scope: str
    issued_at: float
    expires_at: float
    revoked_at_finish: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "secret_ref", _token("secret_ref", self.secret_ref))
        object.__setattr__(self, "scope", _token("scope", self.scope))
        issued = _time("issued_at", self.issued_at)
        expires = _time("expires_at", self.expires_at)
        if expires <= issued:
            raise SandboxLifecycleError("secret projection expiry must follow issuance")
        if not isinstance(self.revoked_at_finish, bool):
            raise TypeError("revoked_at_finish must be boolean")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)

    def as_dict(self) -> dict[str, object]:
        return {
            "secret_ref": self.secret_ref,
            "scope": self.scope,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "revoked_at_finish": self.revoked_at_finish,
        }


@dataclass(frozen=True, slots=True)
class ArtifactScanEvidence:
    artifact_digest: str
    scanner_id: str
    policy_digest: str
    passed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_digest", _sha("artifact_digest", self.artifact_digest))
        object.__setattr__(self, "scanner_id", _token("scanner_id", self.scanner_id))
        object.__setattr__(self, "policy_digest", _sha("policy_digest", self.policy_digest))
        if not isinstance(self.passed, bool):
            raise TypeError("passed must be boolean")

    def as_dict(self) -> dict[str, object]:
        return {
            "artifact_digest": self.artifact_digest,
            "scanner_id": self.scanner_id,
            "policy_digest": self.policy_digest,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class SandboxLifecycleEvidence:
    execution_id: str
    backend_id: str
    isolation_mode: str
    control_plane_pid: int
    sandbox_pid: int
    workdir_id: str
    workdir_ephemeral: bool
    cleanup_attempted: bool
    cleanup_verified: bool
    clean_environment: bool
    ambient_credentials_present: bool
    network_isolated: bool
    child_process_policy: str
    started_at: float
    deadline_at: float
    finished_at: float
    output_bytes: int
    max_output_bytes: int
    secret_projections: tuple[SecretProjectionEvidence, ...] = ()
    artifact_scans: tuple[ArtifactScanEvidence, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("execution_id", "backend_id", "workdir_id"):
            object.__setattr__(self, field_name, _token(field_name, getattr(self, field_name)))
        mode = _text("isolation_mode", self.isolation_mode, maximum=64)
        if mode not in _ALLOWED_MODES:
            raise SandboxLifecycleError("unsupported isolation_mode")
        object.__setattr__(self, "isolation_mode", mode)
        child_policy = _text("child_process_policy", self.child_process_policy, maximum=64)
        if child_policy not in _ALLOWED_CHILD_POLICIES:
            raise SandboxLifecycleError("unsupported child_process_policy")
        object.__setattr__(self, "child_process_policy", child_policy)

        for field_name in ("control_plane_pid", "sandbox_pid"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise SandboxLifecycleError(f"{field_name} must be a positive integer")

        for field_name in (
            "workdir_ephemeral",
            "cleanup_attempted",
            "cleanup_verified",
            "clean_environment",
            "ambient_credentials_present",
            "network_isolated",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be boolean")

        started = _time("started_at", self.started_at)
        deadline = _time("deadline_at", self.deadline_at)
        finished = _time("finished_at", self.finished_at)
        if deadline <= started:
            raise SandboxLifecycleError("deadline_at must follow started_at")
        if finished < started:
            raise SandboxLifecycleError("finished_at cannot precede started_at")
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "deadline_at", deadline)
        object.__setattr__(self, "finished_at", finished)

        for field_name in ("output_bytes", "max_output_bytes"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise SandboxLifecycleError(f"{field_name} must be a non-negative integer")
        if self.max_output_bytes <= 0:
            raise SandboxLifecycleError("max_output_bytes must be positive")

        projections = tuple(self.secret_projections)
        scans = tuple(self.artifact_scans)
        if any(not isinstance(item, SecretProjectionEvidence) for item in projections):
            raise TypeError("secret_projections must contain SecretProjectionEvidence")
        if any(not isinstance(item, ArtifactScanEvidence) for item in scans):
            raise TypeError("artifact_scans must contain ArtifactScanEvidence")
        refs = [item.secret_ref for item in projections]
        digests = [item.artifact_digest for item in scans]
        if len(refs) != len(set(refs)):
            raise SandboxLifecycleError("secret projection refs must be unique")
        if len(digests) != len(set(digests)):
            raise SandboxLifecycleError("artifact scan digests must be unique")
        object.__setattr__(self, "secret_projections", projections)
        object.__setattr__(self, "artifact_scans", scans)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.sandbox_lifecycle_evidence.v1",
            "execution_id": self.execution_id,
            "backend_id": self.backend_id,
            "isolation_mode": self.isolation_mode,
            "control_plane_pid": self.control_plane_pid,
            "sandbox_pid": self.sandbox_pid,
            "workdir_id": self.workdir_id,
            "workdir_ephemeral": self.workdir_ephemeral,
            "cleanup_attempted": self.cleanup_attempted,
            "cleanup_verified": self.cleanup_verified,
            "clean_environment": self.clean_environment,
            "ambient_credentials_present": self.ambient_credentials_present,
            "network_isolated": self.network_isolated,
            "child_process_policy": self.child_process_policy,
            "started_at": self.started_at,
            "deadline_at": self.deadline_at,
            "finished_at": self.finished_at,
            "output_bytes": self.output_bytes,
            "max_output_bytes": self.max_output_bytes,
            "secret_projections": [item.as_dict() for item in self.secret_projections],
            "artifact_scans": [item.as_dict() for item in self.artifact_scans],
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class SandboxLifecycleReport:
    accepted: bool
    evidence_digest: str
    reasons: tuple[str, ...]

    def require_accepted(self) -> "SandboxLifecycleReport":
        if not self.accepted:
            raise SandboxLifecycleError(
                "sandbox lifecycle rejected: " + ",".join(self.reasons)
            )
        return self


def verify_sandbox_lifecycle(
    evidence: SandboxLifecycleEvidence,
    *,
    required_artifact_digests: Iterable[str] = (),
    require_network_isolation: bool,
) -> SandboxLifecycleReport:
    if not isinstance(evidence, SandboxLifecycleEvidence):
        raise TypeError("evidence must be SandboxLifecycleEvidence")

    required = tuple(sorted({_sha("required artifact digest", item) for item in required_artifact_digests}))
    reasons: list[str] = []

    if evidence.control_plane_pid == evidence.sandbox_pid:
        reasons.append("execution-not-out-of-process")
    if not evidence.workdir_ephemeral:
        reasons.append("workdir-not-ephemeral")
    if not evidence.cleanup_attempted:
        reasons.append("cleanup-not-attempted")
    if not evidence.cleanup_verified:
        reasons.append("cleanup-not-verified")
    if not evidence.clean_environment:
        reasons.append("environment-not-clean")
    if evidence.ambient_credentials_present:
        reasons.append("ambient-credentials-present")
    if require_network_isolation and not evidence.network_isolated:
        reasons.append("network-not-isolated")
    if evidence.finished_at > evidence.deadline_at:
        reasons.append("execution-deadline-exceeded")
    if evidence.output_bytes > evidence.max_output_bytes:
        reasons.append("output-budget-exceeded")

    for projection in evidence.secret_projections:
        if projection.issued_at < evidence.started_at:
            reasons.append(f"secret-projection-before-execution:{projection.secret_ref}")
        if projection.expires_at > evidence.deadline_at:
            reasons.append(f"secret-projection-outlives-deadline:{projection.secret_ref}")
        if not projection.revoked_at_finish:
            reasons.append(f"secret-projection-not-revoked:{projection.secret_ref}")

    scans = {item.artifact_digest: item for item in evidence.artifact_scans}
    for digest in required:
        scan = scans.get(digest)
        if scan is None:
            reasons.append(f"artifact-scan-missing:{digest}")
        elif not scan.passed:
            reasons.append(f"artifact-scan-failed:{digest}")
    for scan in evidence.artifact_scans:
        if not scan.passed:
            reasons.append(f"artifact-scan-failed:{scan.artifact_digest}")

    return SandboxLifecycleReport(
        accepted=not reasons,
        evidence_digest=evidence.digest,
        reasons=tuple(sorted(set(reasons))),
    )


__all__ = [
    "ArtifactScanEvidence",
    "SandboxLifecycleError",
    "SandboxLifecycleEvidence",
    "SandboxLifecycleReport",
    "SecretProjectionEvidence",
    "verify_sandbox_lifecycle",
]
