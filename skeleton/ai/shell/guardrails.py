"""Deterministic validation of untrusted model output."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Mapping

from skeleton.shells.ai.types import AIIntent, AIPlanProposal


class GuardrailSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class GuardrailFinding:
    severity: GuardrailSeverity
    code: str
    action_id: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "action_id": self.action_id,
            "message": self.message,
        }


@dataclass(frozen=True)
class GuardrailReport:
    findings: tuple[GuardrailFinding, ...]

    @property
    def errors(self) -> int:
        return sum(item.severity is GuardrailSeverity.ERROR for item in self.findings)

    @property
    def warnings(self) -> int:
        return sum(item.severity is GuardrailSeverity.WARNING for item in self.findings)

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


_SHELL_META = re.compile(r"(?:;|\|\||&&|\x60|\$\(|>|<)")
_INTERPRETER_FLAGS = {
    "python": {"-c", "-m"},
    "python3": {"-c", "-m"},
    "bash": {"-c"},
    "sh": {"-c"},
    "node": {"-e", "--eval"},
    "ruby": {"-e"},
}


class ModelOutputGuard:
    """Find risky model-output shapes before ordinary command admission."""

    def inspect(self, intent: AIIntent, proposal: AIPlanProposal) -> GuardrailReport:
        findings: list[GuardrailFinding] = []
        if proposal.intent_id != intent.intent_id:
            findings.append(
                GuardrailFinding(
                    GuardrailSeverity.ERROR,
                    "intent_mismatch",
                    "",
                    "proposal intent_id does not match request",
                )
            )
        for action in proposal.actions:
            if not intent.constraint.allows_command(action.command):
                findings.append(
                    GuardrailFinding(
                        GuardrailSeverity.ERROR,
                        "command_constraint",
                        action.action_id,
                        "logical command violates intent command constraints",
                    )
                )
            if (
                action.timeout_seconds is not None
                and action.timeout_seconds > intent.constraint.max_timeout_seconds
            ):
                findings.append(
                    GuardrailFinding(
                        GuardrailSeverity.ERROR,
                        "timeout_constraint",
                        action.action_id,
                        "requested timeout exceeds intent constraint",
                    )
                )
            for arg in action.args:
                if _SHELL_META.search(arg):
                    findings.append(
                        GuardrailFinding(
                            GuardrailSeverity.WARNING,
                            "shell_metacharacter",
                            action.action_id,
                            "argument contains shell-like metacharacters; argv semantics remain literal",
                        )
                    )
            interpreter = action.command.lower()
            risky_flags = _INTERPRETER_FLAGS.get(interpreter, set())
            if risky_flags & set(action.args):
                findings.append(
                    GuardrailFinding(
                        GuardrailSeverity.WARNING,
                        "interpreter_code",
                        action.action_id,
                        "action invokes an interpreter code or module entry point",
                    )
                )
            if action.environment_refs:
                findings.append(
                    GuardrailFinding(
                        GuardrailSeverity.INFO,
                        "environment_reference",
                        action.action_id,
                        "action requests opaque environment references",
                    )
                )
        if len(proposal.actions) > intent.constraint.max_steps:
            findings.append(
                GuardrailFinding(
                    GuardrailSeverity.ERROR,
                    "step_limit",
                    "",
                    "proposal exceeds intent step limit",
                )
            )
        return GuardrailReport(tuple(findings))

    def validate_free_form_payload(self, payload: Mapping[str, object]) -> GuardrailReport:
        forbidden = {"shell", "shell_command", "command_line", "raw_command", "script"}
        findings = []
        for key in payload:
            if str(key).lower() in forbidden:
                findings.append(
                    GuardrailFinding(
                        GuardrailSeverity.ERROR,
                        "free_form_shell",
                        "",
                        f"model output field {key!r} is not accepted",
                    )
                )
        return GuardrailReport(tuple(findings))
