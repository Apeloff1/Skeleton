"""Capability grants for host execution.

The shell plane treats process execution as an explicit capability set.  A
caller can ask for a narrower grant, but no helper in this module can widen a
grant by accident.  This gives higher-level agent/tool code a small authority
object to pass around instead of boolean "trusted" flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from skeleton.shells.errors import CapabilityDenied, ShellErrorCode, ShellErrorContext


class ShellCapability(str, Enum):
    EXECUTE = "execute"
    CUSTOM_ENV = "custom_env"
    INHERIT_ENV = "inherit_env"
    STDIN = "stdin"
    NONZERO_SUCCESS = "nonzero_success"
    LONG_RUNNING = "long_running"
    LARGE_OUTPUT = "large_output"
    PARALLEL = "parallel"
    PIPELINE = "pipeline"
    RETRY = "retry"
    AUDIT_EXPORT = "audit_export"
    MANIFEST = "manifest"


@dataclass(frozen=True)
class CapabilityGrant:
    """Immutable authority token for shell-plane operations."""

    capabilities: frozenset[ShellCapability]
    principal: str = "anonymous"
    scope: str = "shell"

    @classmethod
    def none(cls, *, principal: str = "anonymous", scope: str = "shell") -> "CapabilityGrant":
        return cls(frozenset(), principal=principal, scope=scope)

    @classmethod
    def execution_only(cls, *, principal: str = "anonymous") -> "CapabilityGrant":
        return cls(frozenset({ShellCapability.EXECUTE}), principal=principal)

    @classmethod
    def from_names(
        cls,
        names: Iterable[str],
        *,
        principal: str = "anonymous",
        scope: str = "shell",
    ) -> "CapabilityGrant":
        parsed: set[ShellCapability] = set()
        for name in names:
            try:
                parsed.add(ShellCapability(str(name)))
            except ValueError as exc:
                raise ValueError(f"unknown shell capability: {name!r}") from exc
        return cls(frozenset(parsed), principal=principal, scope=scope)

    def has(self, capability: ShellCapability) -> bool:
        return capability in self.capabilities

    def require(
        self,
        capability: ShellCapability,
        *,
        command: str | None = None,
        detail: str = "",
    ) -> None:
        if self.has(capability):
            return
        raise CapabilityDenied(
            ShellErrorContext(
                ShellErrorCode.CAPABILITY,
                command=command,
                detail=detail or f"missing {capability.value} capability",
            )
        )

    def require_all(
        self,
        capabilities: Iterable[ShellCapability],
        *,
        command: str | None = None,
    ) -> None:
        missing = sorted(cap.value for cap in capabilities if cap not in self.capabilities)
        if not missing:
            return
        raise CapabilityDenied(
            ShellErrorContext(
                ShellErrorCode.CAPABILITY,
                command=command,
                detail="missing capabilities: " + ", ".join(missing),
            )
        )

    def narrow(self, capabilities: Iterable[ShellCapability], *, scope: str | None = None) -> "CapabilityGrant":
        requested = frozenset(capabilities)
        if not requested <= self.capabilities:
            missing = sorted(cap.value for cap in requested - self.capabilities)
            raise CapabilityDenied(
                ShellErrorContext(
                    ShellErrorCode.CAPABILITY,
                    detail="cannot widen grant with: " + ", ".join(missing),
                )
            )
        return CapabilityGrant(
            requested,
            principal=self.principal,
            scope=self.scope if scope is None else scope,
        )

    def intersect(self, other: "CapabilityGrant", *, scope: str | None = None) -> "CapabilityGrant":
        principal = self.principal if self.principal == other.principal else "composed"
        return CapabilityGrant(
            self.capabilities & other.capabilities,
            principal=principal,
            scope=scope or self.scope,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "capabilities": sorted(cap.value for cap in self.capabilities),
            "principal": self.principal,
            "scope": self.scope,
        }
