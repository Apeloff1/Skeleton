"""Capability-based sandbox contract for agent tool execution.

This module defines the policy boundary for sensitive tool capabilities.  It is
intentionally dependency-free and fail-closed: tools declare the capabilities
they require, executions receive an explicit grant set, and undeclared ambient
process authority is never treated as permission.

The contract is a policy gate rather than an operating-system sandbox.  Tool
runners are expected to route sensitive operations through this gate and can
seal the emitted audit records into the repository's broader provenance path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping


class CapabilityDenied(PermissionError):
    """Raised when a tool requests a capability not present in its grant."""


class ToolCapability(str, Enum):
    """Sensitive capability classes understood by the agent tool sandbox."""

    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"
    NETWORK = "network"
    PROCESS_EXEC = "process.exec"
    SECRETS_READ = "secrets.read"
    REPOSITORY_MUTATION = "repository.mutation"

    @classmethod
    def parse(cls, value: "ToolCapability | str") -> "ToolCapability":
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError("tool capability must be a string or ToolCapability")
        normalized = value.strip().lower()
        if normalized != value:
            raise ValueError("tool capability must already be normalized")
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(f"unknown tool capability: {value!r}") from exc


def _capability_set(
    values: Iterable[ToolCapability | str],
) -> frozenset[ToolCapability]:
    if isinstance(values, (str, bytes)):
        raise TypeError("capabilities must be an iterable, not a string")
    return frozenset(ToolCapability.parse(value) for value in values)


@dataclass(frozen=True, slots=True)
class ToolMetadata:
    """Security metadata declared by a tool at registration time."""

    name: str
    required_capabilities: frozenset[ToolCapability] = field(default_factory=frozenset)
    mutates: bool = False
    approval_required: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name or self.name.strip() != self.name:
            raise ValueError("tool name must be a non-empty normalized string")
        object.__setattr__(
            self,
            "required_capabilities",
            _capability_set(self.required_capabilities),
        )
        if not isinstance(self.mutates, bool):
            raise TypeError("tool mutates flag must be boolean")
        if not isinstance(self.approval_required, bool):
            raise TypeError("tool approval_required flag must be boolean")

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required_capabilities": sorted(
                capability.value for capability in self.required_capabilities
            ),
            "mutates": self.mutates,
            "approval_required": self.approval_required,
        }


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    """Explicit capabilities granted to one execution context."""

    capabilities: frozenset[ToolCapability] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "capabilities", _capability_set(self.capabilities))

    @classmethod
    def deny_all(cls) -> "CapabilityGrant":
        return cls()

    @classmethod
    def of(cls, *capabilities: ToolCapability | str) -> "CapabilityGrant":
        return cls(frozenset(capabilities))

    def permits(self, capability: ToolCapability | str) -> bool:
        return ToolCapability.parse(capability) in self.capabilities


@dataclass(frozen=True, slots=True)
class ToolRunContext:
    """Stable identifiers attached to every sandbox decision and invocation."""

    run_id: str
    build_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id or self.run_id.strip() != self.run_id:
            raise ValueError("run_id must be a non-empty normalized string")
        if self.build_id is not None and (
            not isinstance(self.build_id, str)
            or not self.build_id
            or self.build_id.strip() != self.build_id
        ):
            raise ValueError("build_id must be null or a non-empty normalized string")


@dataclass(frozen=True, slots=True)
class SandboxAuditEvent:
    """Structured audit evidence for a capability decision or tool invocation."""

    kind: str
    tool: str
    decision: str
    run_id: str
    build_id: str | None = None
    capability: str | None = None
    error_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "tool": self.tool,
            "decision": self.decision,
            "run_id": self.run_id,
            "build_id": self.build_id,
        }
        if self.capability is not None:
            payload["capability"] = self.capability
        if self.error_type is not None:
            payload["error_type"] = self.error_type
        return payload


AuditSink = Callable[[SandboxAuditEvent], None]


class CapabilitySandbox:
    """Authorize and invoke tools against explicit capability grants."""

    def __init__(self, audit_sink: AuditSink | None = None) -> None:
        self._audit_sink = audit_sink
        self._events: list[SandboxAuditEvent] = []

    def _emit(self, event: SandboxAuditEvent) -> None:
        self._events.append(event)
        if self._audit_sink is not None:
            self._audit_sink(event)

    def audit(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self._events]

    def authorize(
        self,
        metadata: ToolMetadata,
        *,
        context: ToolRunContext,
        grant: CapabilityGrant | None = None,
    ) -> None:
        if not isinstance(metadata, ToolMetadata):
            raise TypeError("metadata must be ToolMetadata")
        if not isinstance(context, ToolRunContext):
            raise TypeError("context must be ToolRunContext")
        active_grant = grant or CapabilityGrant.deny_all()
        if not isinstance(active_grant, CapabilityGrant):
            raise TypeError("grant must be CapabilityGrant or None")

        missing: list[str] = []
        for capability in sorted(
            metadata.required_capabilities, key=lambda item: item.value
        ):
            allowed = active_grant.permits(capability)
            self._emit(
                SandboxAuditEvent(
                    kind="capability.decision",
                    tool=metadata.name,
                    capability=capability.value,
                    decision="allow" if allowed else "deny",
                    run_id=context.run_id,
                    build_id=context.build_id,
                )
            )
            if not allowed:
                missing.append(capability.value)

        if missing:
            required = ", ".join(missing)
            raise CapabilityDenied(
                f"tool {metadata.name!r} missing required capabilities: {required}"
            )

    def invoke(
        self,
        metadata: ToolMetadata,
        handler: Callable[..., Any],
        *,
        context: ToolRunContext,
        grant: CapabilityGrant | None = None,
        kwargs: Mapping[str, Any] | None = None,
    ) -> Any:
        if not callable(handler):
            raise TypeError("tool handler must be callable")
        self.authorize(metadata, context=context, grant=grant)
        self._emit(
            SandboxAuditEvent(
                kind="tool.invoke",
                tool=metadata.name,
                decision="start",
                run_id=context.run_id,
                build_id=context.build_id,
            )
        )
        try:
            result = handler(**dict(kwargs or {}))
        except Exception as exc:
            self._emit(
                SandboxAuditEvent(
                    kind="tool.invoke",
                    tool=metadata.name,
                    decision="error",
                    run_id=context.run_id,
                    build_id=context.build_id,
                    error_type=type(exc).__name__,
                )
            )
            raise
        self._emit(
            SandboxAuditEvent(
                kind="tool.invoke",
                tool=metadata.name,
                decision="success",
                run_id=context.run_id,
                build_id=context.build_id,
            )
        )
        return result
