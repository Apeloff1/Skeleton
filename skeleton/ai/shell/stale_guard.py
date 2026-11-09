"""Detect stale AI plans before they cross into execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.compiler import CompiledAIPlan
from skeleton.shells.ai.effects import EffectRegistry
from skeleton.shells.ai.policy_store import AIPolicyRevision
from skeleton.shells.ai.schema import schema_digest
from skeleton.shells.ai.types import AIIntent, AIPlanProposal


class StalenessKind(str, Enum):
    INTENT = "intent"
    PROPOSAL = "proposal"
    TOOL_CATALOG = "tool_catalog"
    EFFECTS = "effects"
    POLICY = "policy"
    SCHEMA = "schema"
    PLAN = "plan"


@dataclass(frozen=True)
class StalenessFinding:
    kind: StalenessKind
    expected: str
    observed: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind.value,
            "expected": self.expected,
            "observed": self.observed,
            "message": self.message,
        }


@dataclass(frozen=True)
class StalenessReport:
    findings: tuple[StalenessFinding, ...]

    @property
    def stale(self) -> bool:
        return bool(self.findings)

    @property
    def ok(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict[str, object]:
        return {
            "stale": self.stale,
            "findings": [item.to_dict() for item in self.findings],
        }


@dataclass(frozen=True)
class PlanPin:
    intent_fingerprint: str
    proposal_fingerprint: str
    tool_catalog_digest: str
    effect_digest: str
    policy_fingerprint: str
    schema_digest: str
    plan_fingerprint: str

    def to_dict(self) -> dict[str, str]:
        return {
            "intent_fingerprint": self.intent_fingerprint,
            "proposal_fingerprint": self.proposal_fingerprint,
            "tool_catalog_digest": self.tool_catalog_digest,
            "effect_digest": self.effect_digest,
            "policy_fingerprint": self.policy_fingerprint,
            "schema_digest": self.schema_digest,
            "plan_fingerprint": self.plan_fingerprint,
        }


class AIPlanStaleGuard:
    """Pin the exact planning surface and revalidate it before execution."""

    @staticmethod
    def pin(
        intent: AIIntent,
        proposal: AIPlanProposal,
        compiled: CompiledAIPlan,
        catalog: AIToolCatalog,
        effects: EffectRegistry,
        policy: AIPolicyRevision,
    ) -> PlanPin:
        return PlanPin(
            intent.fingerprint,
            proposal.fingerprint,
            catalog.digest,
            effects.digest,
            policy.fingerprint,
            schema_digest(),
            compiled.plan.fingerprint,
        )

    @staticmethod
    def inspect(
        pin: PlanPin,
        *,
        intent: AIIntent,
        proposal: AIPlanProposal,
        compiled: CompiledAIPlan,
        catalog: AIToolCatalog,
        effects: EffectRegistry,
        policy: AIPolicyRevision,
    ) -> StalenessReport:
        findings: list[StalenessFinding] = []

        def compare(kind: StalenessKind, expected: str, observed: str, message: str) -> None:
            if expected != observed:
                findings.append(StalenessFinding(kind, expected, observed, message))

        compare(
            StalenessKind.INTENT,
            pin.intent_fingerprint,
            intent.fingerprint,
            "intent changed after planning",
        )
        compare(
            StalenessKind.PROPOSAL,
            pin.proposal_fingerprint,
            proposal.fingerprint,
            "proposal changed after review",
        )
        compare(
            StalenessKind.TOOL_CATALOG,
            pin.tool_catalog_digest,
            catalog.digest,
            "model-visible tool catalog changed after planning",
        )
        compare(
            StalenessKind.EFFECTS,
            pin.effect_digest,
            effects.digest,
            "effect contracts changed after planning",
        )
        compare(
            StalenessKind.POLICY,
            pin.policy_fingerprint,
            policy.fingerprint,
            "AI autonomy policy changed after planning",
        )
        compare(
            StalenessKind.SCHEMA,
            pin.schema_digest,
            schema_digest(),
            "AI model protocol schema changed after planning",
        )
        compare(
            StalenessKind.PLAN,
            pin.plan_fingerprint,
            compiled.plan.fingerprint,
            "compiled execution plan changed after review",
        )
        return StalenessReport(tuple(findings))

    @classmethod
    def require_current(cls, pin: PlanPin, **kwargs) -> None:
        report = cls.inspect(pin, **kwargs)
        if report.stale:
            kinds = ", ".join(item.kind.value for item in report.findings)
            raise RuntimeError(f"AI shell plan is stale: {kinds}")
