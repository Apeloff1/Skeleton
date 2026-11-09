from __future__ import annotations

import hashlib

import pytest

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.security.capability_contracts import CapabilityGrant, SecurityContractError
from skeleton.security.tool_authorization import (
    AuthorizationReceipt,
    SecurityContext,
    ToolRequest,
    authorize_tool_request,
)


D = "0" * 64


def _grant() -> CapabilityGrant:
    return CapabilityGrant(
        principal_id="worker-1",
        capability="repo.read",
        resource="repo:a",
        operation="read",
    )


def _context(*grants: CapabilityGrant) -> SecurityContext:
    return SecurityContext(
        principal_id="worker-1",
        context_id="ctx-1",
        grants=grants or (_grant(),),
    )


def _request(
    *,
    capability: str = "repo.read",
    resource: str = "repo:a",
    operation: str = "read",
) -> ToolRequest:
    return ToolRequest(
        tool_id="git",
        capability=capability,
        resource=resource,
        operation=operation,
        request_digest=D,
    )


def test_exact_grant_authorizes_one_tool_request() -> None:
    receipt = authorize_tool_request(_context(), _request())

    assert receipt.context_id == "ctx-1"
    assert receipt.tool_id == "git"
    assert receipt.request_digest == D
    assert receipt.scope == "single-tool-request"


@pytest.mark.parametrize(
    ("capability", "resource", "operation"),
    (
        ("repo.write", "repo:a", "read"),
        ("repo.read", "repo:b", "read"),
        ("repo.read", "repo:a", "write"),
    ),
)
def test_capability_resource_operation_mismatch_denied(
    capability: str,
    resource: str,
    operation: str,
) -> None:
    with pytest.raises(SecurityContractError, match="request not authorized"):
        authorize_tool_request(
            _context(),
            _request(
                capability=capability,
                resource=resource,
                operation=operation,
            ),
        )


def test_duplicate_exact_grants_fail_closed_as_ambiguous() -> None:
    grant = _grant()
    with pytest.raises(SecurityContractError, match="request not authorized"):
        authorize_tool_request(_context(grant, grant), _request())


def test_foreign_principal_grant_is_rejected() -> None:
    foreign = CapabilityGrant(
        principal_id="worker-2",
        capability="repo.read",
        resource="repo:a",
        operation="read",
    )
    with pytest.raises(SecurityContractError, match="foreign grant"):
        _context(foreign)


def test_receipt_scope_cannot_expand_to_session() -> None:
    receipt = authorize_tool_request(_context(), _request())
    with pytest.raises(SecurityContractError, match="invalid authorization scope"):
        AuthorizationReceipt(
            context_id=receipt.context_id,
            tool_id=receipt.tool_id,
            request_digest=receipt.request_digest,
            grant_digest=receipt.grant_digest,
            scope="session",
        )


def test_grant_identity_uses_shared_canonical_contract_bytes() -> None:
    grant = _grant()
    expected = hashlib.sha256(
        canonical_json_bytes(
            {
                "principal_id": grant.principal_id,
                "capability": grant.capability,
                "resource": grant.resource,
                "operation": grant.operation,
            }
        )
    ).hexdigest()

    receipt = authorize_tool_request(_context(grant), _request())
    assert receipt.grant_digest == expected


def test_tool_authorization_source_and_ai_mirror_are_byte_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton/security/tool_authorization.py"
    mirror = root / "skeleton/ai/runtime/security/tool_authorization.py"

    assert source.read_bytes() == mirror.read_bytes()



@pytest.mark.parametrize(
    "factory",
    (
        lambda: SecurityContext(" worker-1", "ctx-1", (_grant(),)),
        lambda: SecurityContext("worker-1", "", (_grant(),)),
        lambda: ToolRequest("git", "", "repo:a", "read", D),
        lambda: ToolRequest(" git", "repo.read", "repo:a", "read", D),
    ),
)
def test_malformed_runtime_authorization_inputs_fail_closed(factory) -> None:
    with pytest.raises(SecurityContractError):
        factory()
