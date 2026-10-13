"""Declarative resource ceilings for AI-directed sandbox execution."""

from __future__ import annotations

from dataclasses import dataclass
import math

from skeleton.shells.ai.risk import RiskAssessment, RiskBand
from skeleton.shells.ai.types import AIIntent, AIPlanProposal


@dataclass(frozen=True)
class AIResourceProfile:
    wall_seconds: float
    cpu_seconds: float
    memory_bytes: int
    process_count: int
    file_bytes: int
    open_files: int
    output_bytes: int

    def __post_init__(self) -> None:
        if self.wall_seconds <= 0 or not math.isfinite(self.wall_seconds):
            raise ValueError("wall_seconds must be finite and positive")
        if self.cpu_seconds <= 0 or not math.isfinite(self.cpu_seconds):
            raise ValueError("cpu_seconds must be finite and positive")
        for name in (
            "memory_bytes",
            "process_count",
            "file_bytes",
            "open_files",
            "output_bytes",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")

    def no_wider_than(self, parent: "AIResourceProfile") -> bool:
        return (
            self.wall_seconds <= parent.wall_seconds
            and self.cpu_seconds <= parent.cpu_seconds
            and self.memory_bytes <= parent.memory_bytes
            and self.process_count <= parent.process_count
            and self.file_bytes <= parent.file_bytes
            and self.open_files <= parent.open_files
            and self.output_bytes <= parent.output_bytes
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "wall_seconds": self.wall_seconds,
            "cpu_seconds": self.cpu_seconds,
            "memory_bytes": self.memory_bytes,
            "process_count": self.process_count,
            "file_bytes": self.file_bytes,
            "open_files": self.open_files,
            "output_bytes": self.output_bytes,
        }


@dataclass(frozen=True)
class AIResourcePolicy:
    low: AIResourceProfile = AIResourceProfile(
        wall_seconds=60,
        cpu_seconds=30,
        memory_bytes=512 * 1024 * 1024,
        process_count=32,
        file_bytes=256 * 1024 * 1024,
        open_files=256,
        output_bytes=4 * 1024 * 1024,
    )
    medium: AIResourceProfile = AIResourceProfile(
        wall_seconds=45,
        cpu_seconds=20,
        memory_bytes=384 * 1024 * 1024,
        process_count=24,
        file_bytes=128 * 1024 * 1024,
        open_files=192,
        output_bytes=2 * 1024 * 1024,
    )
    high: AIResourceProfile = AIResourceProfile(
        wall_seconds=30,
        cpu_seconds=10,
        memory_bytes=256 * 1024 * 1024,
        process_count=16,
        file_bytes=64 * 1024 * 1024,
        open_files=128,
        output_bytes=1024 * 1024,
    )
    critical: AIResourceProfile = AIResourceProfile(
        wall_seconds=15,
        cpu_seconds=5,
        memory_bytes=128 * 1024 * 1024,
        process_count=8,
        file_bytes=32 * 1024 * 1024,
        open_files=64,
        output_bytes=512 * 1024,
    )

    def for_band(self, band: RiskBand) -> AIResourceProfile:
        return {
            RiskBand.LOW: self.low,
            RiskBand.MEDIUM: self.medium,
            RiskBand.HIGH: self.high,
            RiskBand.CRITICAL: self.critical,
        }[RiskBand(band)]


@dataclass(frozen=True)
class AIResourceDecision:
    profile: AIResourceProfile
    base_profile: AIResourceProfile
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.to_dict(),
            "base_profile": self.base_profile.to_dict(),
            "reasons": list(self.reasons),
        }


class AIResourceCompiler:
    def __init__(self, policy: AIResourcePolicy | None = None) -> None:
        self.policy = policy or AIResourcePolicy()

    def compile(
        self,
        intent: AIIntent,
        proposal: AIPlanProposal,
        risk: RiskAssessment,
    ) -> AIResourceDecision:
        base = self.policy.for_band(risk.band)
        requested_timeout = max(
            (
                action.timeout_seconds or intent.constraint.max_timeout_seconds
                for action in proposal.actions
            ),
            default=intent.constraint.max_timeout_seconds,
        )
        wall = min(
            base.wall_seconds,
            intent.constraint.max_timeout_seconds * max(1, len(proposal.actions)),
            requested_timeout * max(1, len(proposal.actions)),
        )
        wall = max(0.1, wall)
        cpu = min(base.cpu_seconds, wall)
        profile = AIResourceProfile(
            wall_seconds=wall,
            cpu_seconds=cpu,
            memory_bytes=base.memory_bytes,
            process_count=base.process_count,
            file_bytes=base.file_bytes,
            open_files=base.open_files,
            output_bytes=base.output_bytes,
        )
        reasons = (
            f"resource ceiling selected from {risk.band.value} risk band",
            "wall clock bounded by intent and action timeout ceilings",
        )
        return AIResourceDecision(profile, base, reasons)
