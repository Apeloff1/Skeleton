"""Least-privilege capability authorization for runtime tool requests."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from skeleton.contracts.canonical import canonical_json_bytes

from .contracts import SecurityContractError, SecurityIdentity


_SHA = re.compile(r"^[0-9a-f]{64}$")


def _text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SecurityContractError(f"invalid {field}")
    if len(value) > maximum:
        raise SecurityContractError(f"invalid {field}")
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise SecurityContractError(f"invalid {field}")
    return value


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    principal_id: str
    capability: str
    resource: str
    operation: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "principal_id",
            _text(self.principal_id, "principal_id", maximum=256),
        )
        for field in ("capability", "resource", "operation"):
            object.__setattr__(
                self,
                field,
                _text(getattr(self, field), field),
            )

    @property
    def digest(self) -> str:
        return sha256(
            canonical_json_bytes(
                {
                    "principal_id": self.principal_id,
                    "capability": self.capability,
                    "resource": self.resource,
                    "operation": self.operation,
                }
            )
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class SecurityContext:
    identity: SecurityIdentity
    grants: tuple[CapabilityGrant, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, SecurityIdentity):
            raise SecurityContractError("invalid security context")
        if not isinstance(self.grants, tuple):
            raise SecurityContractError("invalid security context")
        for grant in self.grants:
            if (
                not isinstance(grant, CapabilityGrant)
                or grant.principal_id != self.identity.principal_id
            ):
                raise SecurityContractError("foreign capability grant")
        object.__setattr__(
            self,
            "grants",
            tuple(sorted(self.grants, key=lambda item: item.digest)),
        )

    def authorize(
        self,
        capability: str,
        resource: str,
        operation: str,
    ) -> CapabilityGrant:
        requested = (
            _text(capability, "capability"),
            _text(resource, "resource"),
            _text(operation, "operation"),
        )
        matches = [
            grant
            for grant in self.grants
            if (
                grant.capability,
                grant.resource,
                grant.operation,
            )
            == requested
        ]
        if len(matches) != 1:
            raise SecurityContractError("capability denied")
        return matches[0]


@dataclass(frozen=True, slots=True)
class ToolRequest:
    tool_id: str
    capability: str
    resource: str
    operation: str
    request_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tool_id",
            _text(self.tool_id, "tool_id", maximum=256),
        )
        for field in ("capability", "resource", "operation"):
            object.__setattr__(
                self,
                field,
                _text(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "request_digest",
            _sha256(self.request_digest, "request_digest"),
        )


@dataclass(frozen=True, slots=True)
class AuthorizationReceipt:
    context_id: str
    tool_id: str
    request_digest: str
    grant_digest: str
    authority_scope: str = "tool-request-only"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "context_id",
            _text(self.context_id, "context_id", maximum=256),
        )
        object.__setattr__(
            self,
            "tool_id",
            _text(self.tool_id, "tool_id", maximum=256),
        )
        object.__setattr__(
            self,
            "request_digest",
            _sha256(self.request_digest, "request_digest"),
        )
        object.__setattr__(
            self,
            "grant_digest",
            _sha256(self.grant_digest, "grant_digest"),
        )
        if self.authority_scope != "tool-request-only":
            raise SecurityContractError("authorization scope escalation")


def authorize_tool_request(
    context: SecurityContext,
    request: ToolRequest,
) -> AuthorizationReceipt:
    if not isinstance(context, SecurityContext) or not isinstance(
        request,
        ToolRequest,
    ):
        raise SecurityContractError("typed authorization inputs required")
    grant = context.authorize(
        request.capability,
        request.resource,
        request.operation,
    )
    return AuthorizationReceipt(
        context_id=context.identity.context_id,
        tool_id=request.tool_id,
        request_digest=request.request_digest,
        grant_digest=grant.digest,
    )


__all__ = [
    "AuthorizationReceipt",
    "CapabilityGrant",
    "SecurityContext",
    "ToolRequest",
    "authorize_tool_request",
]
