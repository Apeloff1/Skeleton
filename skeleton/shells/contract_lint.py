"""Static linting for command catalog contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.commands import CommandCatalog, CommandDefinition


class ContractSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class ContractFinding:
    severity: ContractSeverity
    code: str
    command: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "command": self.command,
            "message": self.message,
        }


@dataclass(frozen=True)
class ContractLintReport:
    findings: tuple[ContractFinding, ...]

    @property
    def errors(self) -> int:
        return sum(item.severity is ContractSeverity.ERROR for item in self.findings)

    @property
    def warnings(self) -> int:
        return sum(item.severity is ContractSeverity.WARNING for item in self.findings)

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


class CommandContractLinter:
    """Detect risky or internally inconsistent command definitions."""

    def lint_definition(self, definition: CommandDefinition) -> tuple[ContractFinding, ...]:
        findings: list[ContractFinding] = []
        name = definition.name

        if definition.allow_stdin and not definition.required_capabilities:
            findings.append(
                ContractFinding(
                    ContractSeverity.WARNING,
                    "stdin_without_explicit_capability",
                    name,
                    "stdin is enabled without a command-specific required capability",
                )
            )

        if definition.allow_nonzero_success and not definition.required_capabilities:
            findings.append(
                ContractFinding(
                    ContractSeverity.WARNING,
                    "nonzero_without_explicit_capability",
                    name,
                    "nonzero success is enabled without a command-specific required capability",
                )
            )

        if definition.max_timeout is not None and definition.max_timeout <= 0:
            findings.append(
                ContractFinding(
                    ContractSeverity.ERROR,
                    "invalid_timeout",
                    name,
                    "command timeout must be positive",
                )
            )

        arg_policy = definition.arguments
        if arg_policy.max_args > 256:
            findings.append(
                ContractFinding(
                    ContractSeverity.WARNING,
                    "large_argument_count",
                    name,
                    "command allows more than 256 arguments",
                )
            )
        if arg_policy.max_total_bytes > 128 * 1024:
            findings.append(
                ContractFinding(
                    ContractSeverity.WARNING,
                    "large_argument_bytes",
                    name,
                    "command argument byte limit is unusually large",
                )
            )

        env_policy = definition.environment
        if len(env_policy.allowed_keys) > 128:
            findings.append(
                ContractFinding(
                    ContractSeverity.WARNING,
                    "large_environment_surface",
                    name,
                    "command environment allowlist has high cardinality",
                )
            )
        if env_policy.inherit:
            findings.append(
                ContractFinding(
                    ContractSeverity.INFO,
                    "environment_inheritance",
                    name,
                    "command inherits selected parent environment keys",
                )
            )
        return tuple(findings)

    def lint(self, catalog: CommandCatalog) -> ContractLintReport:
        findings: list[ContractFinding] = []
        for definition in catalog.snapshot():
            findings.extend(self.lint_definition(definition))
        return ContractLintReport(tuple(findings))
