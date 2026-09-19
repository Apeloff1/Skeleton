"""Cross-component diagnostics for AI shell planning configuration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.effects import EffectRegistry
from skeleton.shells.ai.model_port import AIModelPort
from skeleton.shells.ai.policy import AIShellPolicy


class AIDiagnosticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class AIDiagnosticFinding:
    severity: AIDiagnosticSeverity
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class AIDiagnosticsReport:
    findings: tuple[AIDiagnosticFinding, ...]

    @property
    def errors(self) -> int:
        return sum(item.severity is AIDiagnosticSeverity.ERROR for item in self.findings)

    @property
    def warnings(self) -> int:
        return sum(item.severity is AIDiagnosticSeverity.WARNING for item in self.findings)

    @property
    def ok(self) -> bool:
        return self.errors == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "findings": [item.to_dict() for item in self.findings],
        }


class AIShellDiagnostics:
    def __init__(
        self,
        catalog: AIToolCatalog,
        effects: EffectRegistry,
        policy: AIShellPolicy,
        model: AIModelPort,
    ) -> None:
        self.catalog = catalog
        self.effects = effects
        self.policy = policy
        self.model = model

    def inspect(self) -> AIDiagnosticsReport:
        findings = []
        cards = self.catalog.cards()
        effect_commands = {item.command for item in self.effects.snapshot()}
        for card in cards:
            if card.name not in effect_commands:
                findings.append(
                    AIDiagnosticFinding(
                        AIDiagnosticSeverity.ERROR
                        if self.policy.deny_unknown_effects
                        else AIDiagnosticSeverity.WARNING,
                        "missing_effect_contract",
                        f"model-visible command {card.name!r} has no effect contract",
                    )
                )
        orphaned = effect_commands - {card.name for card in cards}
        if orphaned:
            findings.append(
                AIDiagnosticFinding(
                    AIDiagnosticSeverity.INFO,
                    "orphan_effect_contracts",
                    f"{len(orphaned)} effect contracts are not currently model visible",
                )
            )
        if not self.model.capabilities.structured_output:
            findings.append(
                AIDiagnosticFinding(
                    AIDiagnosticSeverity.ERROR,
                    "unstructured_model",
                    "AI shell requires structured model output",
                )
            )
        if not self.model.capabilities.tool_use:
            findings.append(
                AIDiagnosticFinding(
                    AIDiagnosticSeverity.WARNING,
                    "model_without_tool_use",
                    "model does not advertise tool-use capability",
                )
            )
        if not cards:
            findings.append(
                AIDiagnosticFinding(
                    AIDiagnosticSeverity.WARNING,
                    "empty_tool_catalog",
                    "AI shell has no model-visible commands",
                )
            )
        return AIDiagnosticsReport(tuple(findings))
