"""Release/channel enforcement for AI shell service startup."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.release_channel import AIReleaseChannelStore
from skeleton.shells.ai.release_registry import AIReleaseRegistry


@dataclass(frozen=True)
class RuntimeReleaseExpectation:
    channel: str
    code_revision: str
    policy_fingerprint: str
    tool_catalog_digest: str
    effect_digest: str
    provider_attestation_digest: str = ""
    workspace_manifest_digest: str = ""

    def __post_init__(self) -> None:
        if not self.channel or len(self.channel) > 128:
            raise ValueError("invalid runtime release channel")
        if not self.code_revision or len(self.code_revision) > 256:
            raise ValueError("invalid runtime code revision")
        for name in (
            "policy_fingerprint",
            "tool_catalog_digest",
            "effect_digest",
        ):
            if len(getattr(self, name)) != 64:
                raise ValueError(f"{name} must be SHA-256 hex")
        for name in (
            "provider_attestation_digest",
            "workspace_manifest_digest",
        ):
            value = getattr(self, name)
            if value and len(value) != 64:
                raise ValueError(f"{name} must be SHA-256 hex")


@dataclass(frozen=True)
class StartupReleaseReport:
    allowed: bool
    reasons: tuple[str, ...]
    channel_revision: int | None = None
    release_id: str = ""
    release_revision: int | None = None
    evidence_digest: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "channel_revision": self.channel_revision,
            "release_id": self.release_id,
            "release_revision": self.release_revision,
            "evidence_digest": self.evidence_digest,
        }


class AIStartupReleaseGuard:
    """Fail closed if the running worker differs from signed release evidence."""

    def __init__(
        self,
        channels: AIReleaseChannelStore,
        releases: AIReleaseRegistry,
    ) -> None:
        self.channels = channels
        self.releases = releases

    def inspect(
        self,
        expectation: RuntimeReleaseExpectation,
    ) -> StartupReleaseReport:
        current = self.channels.current(expectation.channel)
        if current is None:
            return StartupReleaseReport(
                False,
                ("release channel is not assigned",),
            )
        channel_revision, channel = current
        reasons = []
        try:
            release = self.releases.current(channel.release_id)
        except KeyError:
            return StartupReleaseReport(
                False,
                ("release channel references unknown release",),
                channel_revision=channel_revision,
                release_id=channel.release_id,
            )
        if not release.active:
            reasons.append("release channel references inactive release")
        if release.revision != channel.release_revision:
            reasons.append("release channel revision does not match registry")
        if release.evidence.digest != channel.evidence_digest:
            reasons.append("release channel evidence digest mismatch")
        if release.signature.signature != channel.registry_signature:
            reasons.append("release channel signature mismatch")
        try:
            self.releases.signer.verify(release.signature)
        except Exception:
            reasons.append("release registry signature verification failed")
        evidence = release.evidence
        if not evidence.deployable:
            reasons.append("release safety case is not deployable")
        if evidence.code_revision != expectation.code_revision:
            reasons.append("runtime code revision differs from release evidence")
        if evidence.policy_fingerprint != expectation.policy_fingerprint:
            reasons.append("runtime policy fingerprint differs from release evidence")
        if evidence.tool_catalog_digest != expectation.tool_catalog_digest:
            reasons.append("runtime tool catalog differs from release evidence")
        if evidence.effect_digest != expectation.effect_digest:
            reasons.append("runtime effect registry differs from release evidence")
        if (
            expectation.provider_attestation_digest
            and evidence.provider_attestation_digest
            != expectation.provider_attestation_digest
        ):
            reasons.append("runtime provider attestation differs from release evidence")
        if (
            expectation.workspace_manifest_digest
            and evidence.workspace_manifest_digest
            != expectation.workspace_manifest_digest
        ):
            reasons.append("runtime workspace manifest differs from release evidence")
        return StartupReleaseReport(
            not reasons,
            tuple(reasons),
            channel_revision=channel_revision,
            release_id=release.release_id,
            release_revision=release.revision,
            evidence_digest=evidence.digest,
        )

    def require(
        self,
        expectation: RuntimeReleaseExpectation,
    ) -> StartupReleaseReport:
        report = self.inspect(expectation)
        if not report.allowed:
            raise RuntimeError("; ".join(report.reasons))
        return report
