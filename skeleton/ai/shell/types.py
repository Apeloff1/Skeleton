"""Typed model-facing intent, action, plan, and verification structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import re
from types import MappingProxyType
from typing import Mapping

from skeleton.shells.runner import ShellCommand

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/+-]{0,159}$")


class IntentKind(str, Enum):
    INSPECT = "inspect"
    BUILD = "build"
    TEST = "test"
    MODIFY = "modify"
    REPAIR = "repair"
    MAINTAIN = "maintain"
    DEPLOY = "deploy"
    ANALYZE = "analyze"


@dataclass(frozen=True)
class IntentConstraint:
    """Constraints narrow model behavior and never widen shell authority."""

    allowed_commands: frozenset[str] = frozenset()
    denied_commands: frozenset[str] = frozenset()
    max_steps: int = 16
    max_timeout_seconds: float = 120.0
    allow_network: bool = False
    allow_writes: bool = False
    allow_destructive: bool = False
    require_reversible: bool = False

    def __post_init__(self) -> None:
        allowed = frozenset(self.allowed_commands)
        denied = frozenset(self.denied_commands)
        if allowed & denied:
            raise ValueError("command cannot be both allowed and denied")
        if self.max_steps <= 0 or self.max_steps > 1024:
            raise ValueError("max_steps must be between 1 and 1024")
        if self.max_timeout_seconds <= 0:
            raise ValueError("max_timeout_seconds must be positive")
        object.__setattr__(self, "allowed_commands", allowed)
        object.__setattr__(self, "denied_commands", denied)

    def allows_command(self, command: str) -> bool:
        if command in self.denied_commands:
            return False
        return not self.allowed_commands or command in self.allowed_commands

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed_commands": sorted(self.allowed_commands),
            "denied_commands": sorted(self.denied_commands),
            "max_steps": self.max_steps,
            "max_timeout_seconds": self.max_timeout_seconds,
            "allow_network": self.allow_network,
            "allow_writes": self.allow_writes,
            "allow_destructive": self.allow_destructive,
            "require_reversible": self.require_reversible,
        }


@dataclass(frozen=True)
class VerificationCriterion:
    criterion_id: str
    description: str
    required: bool = True
    command: str = ""
    expected_returncodes: frozenset[int] = frozenset({0})

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.criterion_id):
            raise ValueError("invalid verification criterion id")
        if not self.description or len(self.description) > 1024:
            raise ValueError("invalid verification description")
        codes = frozenset(self.expected_returncodes)
        if not codes or len(codes) > 32:
            raise ValueError("verification return-code set is invalid")
        if any(isinstance(code, bool) or not isinstance(code, int) for code in codes):
            raise ValueError("verification return codes must be integers")
        object.__setattr__(self, "expected_returncodes", codes)

    def to_dict(self) -> dict[str, object]:
        return {
            "criterion_id": self.criterion_id,
            "description": self.description,
            "required": self.required,
            "command": self.command,
            "expected_returncodes": sorted(self.expected_returncodes),
        }


@dataclass(frozen=True)
class AIIntent:
    intent_id: str
    goal: str
    kind: IntentKind = IntentKind.MAINTAIN
    constraint: IntentConstraint = field(default_factory=IntentConstraint)
    success_criteria: tuple[VerificationCriterion, ...] = ()
    context: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.intent_id):
            raise ValueError("invalid intent_id")
        if not isinstance(self.goal, str) or not self.goal.strip() or len(self.goal) > 8192:
            raise ValueError("goal must be non-empty and bounded")
        kind = IntentKind(self.kind)
        criteria = tuple(self.success_criteria)
        if len(criteria) > 128:
            raise ValueError("too many verification criteria")
        ids = [item.criterion_id for item in criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate verification criterion id")
        context = dict(self.context)
        if len(context) > 64:
            raise ValueError("too many intent context fields")
        for key, value in context.items():
            if not isinstance(key, str) or not _ID.fullmatch(key):
                raise ValueError("invalid intent context key")
            if not isinstance(value, str) or len(value) > 2048:
                raise ValueError("invalid intent context value")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "success_criteria", criteria)
        object.__setattr__(self, "context", MappingProxyType(context))

    def to_dict(self) -> dict[str, object]:
        return {
            "intent_id": self.intent_id,
            "goal": self.goal,
            "kind": self.kind.value,
            "constraint": self.constraint.to_dict(),
            "success_criteria": [item.to_dict() for item in self.success_criteria],
            "context": dict(self.context),
        }

    @property
    def fingerprint(self) -> str:
        raw = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class AIAction:
    """One structured model-proposed action with opaque environment references."""

    action_id: str
    command: str
    args: tuple[str, ...] = ()
    cwd: str | None = None
    environment_refs: Mapping[str, str] = field(default_factory=dict)
    timeout_seconds: float | None = None
    depends_on: frozenset[str] = frozenset()
    continue_on_failure: bool = False
    purpose: str = ""

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.action_id):
            raise ValueError("invalid action_id")
        if not self.command or len(self.command) > 128 or not _ID.fullmatch(self.command):
            raise ValueError("invalid logical command")
        args = tuple(self.args)
        if len(args) > 256:
            raise ValueError("too many action arguments")
        total = 0
        for arg in args:
            if not isinstance(arg, str) or "\x00" in arg:
                raise ValueError("invalid action argument")
            total += len(arg.encode("utf-8"))
        if total > 128 * 1024:
            raise ValueError("action arguments exceed byte limit")
        env = dict(self.environment_refs)
        if len(env) > 64:
            raise ValueError("too many environment references")
        for key, ref in env.items():
            if not _ID.fullmatch(key) or not _ID.fullmatch(ref):
                raise ValueError("invalid environment reference")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        deps = frozenset(self.depends_on)
        if self.action_id in deps:
            raise ValueError("action cannot depend on itself")
        if len(self.purpose) > 1024:
            raise ValueError("action purpose too long")
        object.__setattr__(self, "args", args)
        object.__setattr__(self, "environment_refs", MappingProxyType(env))
        object.__setattr__(self, "depends_on", deps)

    def to_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "command": self.command,
            "args": list(self.args),
            "cwd": self.cwd,
            "environment_refs": dict(self.environment_refs),
            "timeout_seconds": self.timeout_seconds,
            "depends_on": sorted(self.depends_on),
            "continue_on_failure": self.continue_on_failure,
            "purpose": self.purpose,
        }

    def to_shell_command(
        self,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> ShellCommand:
        values = dict(environment or {})
        unexpected = set(values) - set(self.environment_refs)
        if unexpected:
            raise ValueError("environment values supplied for undeclared references")
        missing = set(self.environment_refs) - set(values)
        if missing:
            raise ValueError("environment references are unresolved")
        return ShellCommand(
            self.command,
            self.args,
            self.cwd,
            values,
            None,
            self.timeout_seconds,
            frozenset({0}),
        )


@dataclass(frozen=True)
class AIPlanProposal:
    proposal_id: str
    intent_id: str
    actions: tuple[AIAction, ...]
    confidence: float
    uncertainty: float
    assumptions: tuple[str, ...] = ()
    rationale_summary: str = ""
    model_id: str = ""
    protocol_version: int = 1

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.proposal_id) or not _ID.fullmatch(self.intent_id):
            raise ValueError("invalid proposal identity")
        actions = tuple(self.actions)
        if not actions:
            raise ValueError("proposal requires at least one action")
        if len(actions) > 1024:
            raise ValueError("proposal has too many actions")
        ids = [item.action_id for item in actions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate action_id")
        known = set(ids)
        for action in actions:
            unknown = action.depends_on - known
            if unknown:
                raise ValueError("proposal contains unknown dependency")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not 0.0 <= float(self.uncertainty) <= 1.0:
            raise ValueError("uncertainty must be between 0 and 1")
        assumptions = tuple(self.assumptions)
        if len(assumptions) > 64 or any(not isinstance(item, str) or len(item) > 1024 for item in assumptions):
            raise ValueError("invalid assumptions")
        if len(self.rationale_summary) > 4096:
            raise ValueError("rationale summary too long")
        if len(self.model_id) > 256:
            raise ValueError("model_id too long")
        if self.protocol_version <= 0:
            raise ValueError("protocol_version must be positive")
        object.__setattr__(self, "actions", actions)
        object.__setattr__(self, "assumptions", assumptions)

    def to_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "intent_id": self.intent_id,
            "actions": [item.to_dict() for item in self.actions],
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "assumptions": list(self.assumptions),
            "rationale_summary": self.rationale_summary,
            "model_id": self.model_id,
            "protocol_version": self.protocol_version,
        }

    @property
    def fingerprint(self) -> str:
        raw = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()
