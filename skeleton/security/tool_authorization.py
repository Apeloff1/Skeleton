"""Exact-match runtime authorization over capability contracts."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from skeleton.contracts.canonical import canonical_json_bytes

from .capability_contracts import CapabilityGrant, SecurityContractError


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
class SecurityContext:
    principal_id: str
    context_id: str
    grants: tuple[CapabilityGrant, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "principal_id",
            _text(self.principal_id, "principal_id", maximum=256),
        )
        object.__setattr__(
            self,
            "context_id",
            _text(self.context_id, "context_id", maximum=256),
        )
        if not isinstance(self.grants, tuple):
            raise SecurityContractError("grants must be tuple")
        if any(
            not isinstance(grant, CapabilityGrant)
            or grant.principal_id != self.principal_id
            for grant in self.grants
        ):
            raise SecurityContractError("foreign grant")


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
    scope: str = "single-tool-request"

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
        if self.scope != "single-tool-request":
            raise SecurityContractError("invalid authorization scope")


def _grant_digest(grant: CapabilityGrant) -> str:
    return sha256(
        canonical_json_bytes(
            {
                "principal_id": grant.principal_id,
                "capability": grant.capability,
                "resource": grant.resource,
                "operation": grant.operation,
            }
        )
    ).hexdigest()


def authorize_tool_request(
    context: SecurityContext,
    request: ToolRequest,
) -> AuthorizationReceipt:
    if not isinstance(context, SecurityContext) or not isinstance(
        request,
        ToolRequest,
    ):
        raise SecurityContractError("typed inputs required")
    matches = [
        grant
        for grant in context.grants
        if (
            grant.capability,
            grant.resource,
            grant.operation,
        )
        == (
            request.capability,
            request.resource,
            request.operation,
        )
    ]
    if len(matches) != 1:
        raise SecurityContractError("request not authorized")
    return AuthorizationReceipt(
        context_id=context.context_id,
        tool_id=request.tool_id,
        request_digest=request.request_digest,
        grant_digest=_grant_digest(matches[0]),
    )


__all__ = [
    "AuthorizationReceipt",
    "SecurityContext",
    "ToolRequest",
    "authorize_tool_request",
]
