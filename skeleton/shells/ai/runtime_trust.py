"""Deterministic runtime trust epochs for production AI shell workers.

A release check alone is not enough for a long-lived AI worker.  The model
registry, provider attestations, assurance policy, and tool surface can change
after startup.  This module binds those independently mutable authority
surfaces into one deterministic epoch and lets the service fail closed on
runtime drift.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import threading
from typing import Iterable, Protocol

from skeleton.shells.ai.assurance import AIExecutionAssuranceInspector
from skeleton.shells.ai.model_admission import (
    AIModelAdmission,
    ModelAdmissionReport,
    ModelAdmissionRequirement,
)
from skeleton.shells.ai.startup_release import (
    AIStartupReleaseGuard,
    RuntimeReleaseExpectation,
    StartupReleaseReport,
)


def _sha256(name: str, value: str, *, optional: bool = False) -> str:
    if optional and not value:
        return ""
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be SHA-256 hex") from exc
    return value.lower()


@dataclass(frozen=True)
class RuntimeTrustSurface:
    """Current non-secret runtime identity expected by the worker."""

    code_revision: str
    policy_fingerprint: str
    tool_catalog_digest: str
    effect_digest: str
    assurance_policy_digest: str = ""
    workspace_manifest_digest: str = ""

    def __post_init__(self) -> None:
        if not self.code_revision or len(self.code_revision) > 256:
            raise ValueError("invalid runtime trust code_revision")
        object.__setattr__(
            self,
            "policy_fingerprint",
            _sha256("policy_fingerprint", self.policy_fingerprint),
        )
        object.__setattr__(
            self,
            "tool_catalog_digest",
            _sha256("tool_catalog_digest", self.tool_catalog_digest),
        )
        object.__setattr__(
            self,
            "effect_digest",
            _sha256("effect_digest", self.effect_digest),
        )
        object.__setattr__(
            self,
            "assurance_policy_digest",
            _sha256(
                "assurance_policy_digest",
                self.assurance_policy_digest,
                optional=True,
            ),
        )
        object.__setattr__(
            self,
            "workspace_manifest_digest",
            _sha256(
                "workspace_manifest_digest",
                self.workspace_manifest_digest,
                optional=True,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "code_revision": self.code_revision,
            "policy_fingerprint": self.policy_fingerprint,
            "tool_catalog_digest": self.tool_catalog_digest,
            "effect_digest": self.effect_digest,
            "assurance_policy_digest": self.assurance_policy_digest,
            "workspace_manifest_digest": self.workspace_manifest_digest,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, order=True)
class RuntimeModelBinding:
    """One admitted model/provider revision bound into a runtime epoch."""

    registry_id: str
    registry_revision: int
    attestation_digest: str

    def __post_init__(self) -> None:
        if not self.registry_id or len(self.registry_id) > 513:
            raise ValueError("invalid runtime model registry_id")
        if (
            isinstance(self.registry_revision, bool)
            or not isinstance(self.registry_revision, int)
            or self.registry_revision <= 0
        ):
            raise ValueError("runtime model revision must be positive")
        object.__setattr__(
            self,
            "attestation_digest",
            _sha256("attestation_digest", self.attestation_digest),
        )

    @classmethod
    def from_report(cls, report: ModelAdmissionReport) -> "RuntimeModelBinding":
        if not report.allowed or report.registry_revision is None:
            raise ValueError("cannot bind a denied model admission report")
        return cls(
            report.registry_id,
            report.registry_revision,
            report.attestation_digest,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "registry_id": self.registry_id,
            "registry_revision": self.registry_revision,
            "attestation_digest": self.attestation_digest,
        }


@dataclass(frozen=True)
class RuntimeTrustEpoch:
    """Canonical trust identity for one exact worker authority surface."""

    schema_version: int
    surface: RuntimeTrustSurface
    models: tuple[RuntimeModelBinding, ...] = ()
    release_evidence_digest: str = ""
    release_id: str = ""
    release_revision: int | None = None
    release_channel_revision: int | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported runtime trust epoch schema")
        if not isinstance(self.surface, RuntimeTrustSurface):
            raise ValueError("surface must be RuntimeTrustSurface")
        models = tuple(sorted(self.models))
        if len(models) > 128:
            raise ValueError("runtime trust epoch model bound exceeded")
        if len({item.registry_id for item in models}) != len(models):
            raise ValueError("runtime trust epoch contains duplicate model identities")
        object.__setattr__(self, "models", models)
        object.__setattr__(
            self,
            "release_evidence_digest",
            _sha256(
                "release_evidence_digest",
                self.release_evidence_digest,
                optional=True,
            ),
        )
        if self.release_id and len(self.release_id) > 256:
            raise ValueError("release_id too long")
        for name in ("release_revision", "release_channel_revision"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(f"{name} must be positive")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "surface": self.surface.to_dict(),
            "models": [item.to_dict() for item in self.models],
            "release_evidence_digest": self.release_evidence_digest,
            "release_id": self.release_id,
            "release_revision": self.release_revision,
            "release_channel_revision": self.release_channel_revision,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


class DurableRuntimeTrustPinStore(Protocol):
    def pin(
        self,
        scope: str,
        epoch: RuntimeTrustEpoch,
        *,
        reason: str = "startup pin",
    ) -> object: ...

    def require(
        self,
        scope: str,
        epoch_digest: str,
    ) -> object: ...


@dataclass(frozen=True)
class RuntimeTrustReport:
    allowed: bool
    reasons: tuple[str, ...]
    epoch: RuntimeTrustEpoch | None
    release: StartupReleaseReport | None = None
    model_reports: tuple[ModelAdmissionReport, ...] = ()
    expected_epoch_digest: str = ""

    @property
    def epoch_digest(self) -> str:
        return "" if self.epoch is None else self.epoch.digest

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "epoch": None if self.epoch is None else self.epoch.to_dict(),
            "epoch_digest": self.epoch_digest,
            "release": None if self.release is None else self.release.to_dict(),
            "model_reports": [item.to_dict() for item in self.model_reports],
            "expected_epoch_digest": self.expected_epoch_digest,
        }


class AIRuntimeTrustGuard:
    """Pin and continuously re-prove one exact production runtime trust epoch."""

    def __init__(
        self,
        surface: RuntimeTrustSurface,
        *,
        release_guard: AIStartupReleaseGuard | None = None,
        release_expectation: RuntimeReleaseExpectation | None = None,
        model_admission: AIModelAdmission | None = None,
        model_requirements: Iterable[ModelAdmissionRequirement] = (),
        assurance: AIExecutionAssuranceInspector | None = None,
        expected_epoch_digest: str = "",
        durable_store: DurableRuntimeTrustPinStore | None = None,
        durable_scope: str = "",
    ) -> None:
        if not isinstance(surface, RuntimeTrustSurface):
            raise ValueError("surface must be RuntimeTrustSurface")
        if (durable_store is None) != (not durable_scope):
            raise ValueError(
                "durable_store and durable_scope must be configured together"
            )
        if durable_scope and len(durable_scope) > 128:
            raise ValueError("durable_scope too long")
        if (release_guard is None) != (release_expectation is None):
            raise ValueError(
                "release_guard and release_expectation must be configured together"
            )
        requirements = tuple(
            sorted(tuple(model_requirements), key=lambda item: item.registry_id)
        )
        if len(requirements) > 128:
            raise ValueError("runtime model requirement bound exceeded")
        if len({item.registry_id for item in requirements}) != len(requirements):
            raise ValueError("duplicate runtime model requirement")
        if requirements and model_admission is None:
            raise ValueError("model_admission is required for model requirements")
        for requirement in requirements:
            if requirement.tool_catalog_digest != surface.tool_catalog_digest:
                raise ValueError(
                    "model requirement tool catalog differs from runtime surface"
                )
        if assurance is not None:
            if not surface.assurance_policy_digest:
                raise ValueError(
                    "runtime surface must bind configured assurance policy"
                )
            if surface.assurance_policy_digest != assurance.policy.digest:
                raise ValueError(
                    "runtime surface assurance policy digest mismatch"
                )
        elif surface.assurance_policy_digest:
            raise ValueError(
                "runtime surface binds assurance policy but no inspector is configured"
            )
        if release_expectation is not None:
            if release_expectation.code_revision != surface.code_revision:
                raise ValueError(
                    "release expectation code revision differs from runtime surface"
                )
            if release_expectation.policy_fingerprint != surface.policy_fingerprint:
                raise ValueError(
                    "release expectation policy differs from runtime surface"
                )
            if release_expectation.tool_catalog_digest != surface.tool_catalog_digest:
                raise ValueError(
                    "release expectation tools differ from runtime surface"
                )
            if release_expectation.effect_digest != surface.effect_digest:
                raise ValueError(
                    "release expectation effects differ from runtime surface"
                )
            if (
                surface.workspace_manifest_digest
                and release_expectation.workspace_manifest_digest
                != surface.workspace_manifest_digest
            ):
                raise ValueError(
                    "release expectation workspace differs from runtime surface"
                )

        self.surface = surface
        self.release_guard = release_guard
        self.release_expectation = release_expectation
        self.model_admission = model_admission
        self.model_requirements = requirements
        self.assurance = assurance
        self.durable_store = durable_store
        self.durable_scope = durable_scope
        self._expected_epoch_digest = _sha256(
            "expected_epoch_digest",
            expected_epoch_digest,
            optional=True,
        )
        self._lock = threading.RLock()

    @property
    def expected_epoch_digest(self) -> str:
        with self._lock:
            return self._expected_epoch_digest

    def _inspect_release(self) -> StartupReleaseReport | None:
        if self.release_guard is None or self.release_expectation is None:
            return None
        return self.release_guard.inspect(self.release_expectation)

    def _inspect_models(self) -> tuple[ModelAdmissionReport, ...]:
        if self.model_admission is None:
            return ()
        return tuple(
            self.model_admission.inspect(requirement)
            for requirement in self.model_requirements
        )

    def inspect(self) -> RuntimeTrustReport:
        reasons: list[str] = []
        release = self._inspect_release()
        if release is not None and not release.allowed:
            reasons.extend(
                f"release: {reason}"
                for reason in release.reasons
            )

        if self.assurance is not None:
            current_assurance = self.assurance.policy.digest
            if current_assurance != self.surface.assurance_policy_digest:
                reasons.append("assurance policy drift detected")

        model_reports = self._inspect_models()
        bindings: list[RuntimeModelBinding] = []
        for report in model_reports:
            if not report.allowed:
                reasons.extend(
                    f"model {report.registry_id}: {reason}"
                    for reason in report.reasons
                )
                continue
            bindings.append(RuntimeModelBinding.from_report(report))

        epoch = None
        if not reasons:
            epoch = RuntimeTrustEpoch(
                1,
                self.surface,
                tuple(bindings),
                release_evidence_digest=(
                    "" if release is None else release.evidence_digest
                ),
                release_id="" if release is None else release.release_id,
                release_revision=(
                    None if release is None else release.release_revision
                ),
                release_channel_revision=(
                    None if release is None else release.channel_revision
                ),
            )
            expected = self.expected_epoch_digest
            if expected and epoch.digest != expected:
                reasons.append("runtime trust epoch drift detected")

        return RuntimeTrustReport(
            not reasons,
            tuple(reasons),
            epoch,
            release,
            model_reports,
            self.expected_epoch_digest,
        )

    def require(self) -> RuntimeTrustReport:
        report = self.inspect()
        if not report.allowed:
            raise RuntimeError("; ".join(report.reasons))
        if self.durable_store is not None:
            assert report.epoch is not None
            self.durable_store.require(
                self.durable_scope,
                report.epoch.digest,
            )
        return report

    def pin(self) -> RuntimeTrustReport:
        """Pin the current epoch once; subsequent calls must match it exactly."""

        with self._lock:
            report = self.inspect()
            if not report.allowed:
                raise RuntimeError("; ".join(report.reasons))
            assert report.epoch is not None
            if self.durable_store is not None:
                self.durable_store.pin(
                    self.durable_scope,
                    report.epoch,
                    reason="AI shell worker startup",
                )
            if not self._expected_epoch_digest:
                self._expected_epoch_digest = report.epoch.digest
                return RuntimeTrustReport(
                    True,
                    (),
                    report.epoch,
                    report.release,
                    report.model_reports,
                    self._expected_epoch_digest,
                )
            if report.epoch.digest != self._expected_epoch_digest:
                raise RuntimeError("runtime trust epoch drift detected")
            return report

    def require_current(self) -> RuntimeTrustReport:
        if not self.expected_epoch_digest:
            raise RuntimeError("runtime trust epoch has not been pinned")
        return self.require()
