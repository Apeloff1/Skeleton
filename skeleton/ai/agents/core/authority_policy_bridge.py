"""Bridge canonical agent delegation authority into VOL-028 policy evaluation.

This adapter is intentionally one-way and non-executing. It does not mint or
extend authority; it preserves the exact delegated generation, capabilities,
scopes, and expiry while adding the tenant binding required by the unified
user/service/agent evaluator.
"""

from __future__ import annotations

from skeleton.automation.agents.delegation_qualification import (
    AgentDelegationAuthority,
)
from skeleton.vault.authority_policy import (
    AuthorityPolicyError,
    AuthorityPrincipal,
    PrincipalKind,
)


def principal_from_agent_delegation(
    authority: AgentDelegationAuthority,
    *,
    tenant_id: str,
    revoked: bool = False,
) -> AuthorityPrincipal:
    if not isinstance(authority, AgentDelegationAuthority):
        raise TypeError("authority must be AgentDelegationAuthority")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise AuthorityPolicyError("tenant_id must be non-empty")
    if tenant_id != tenant_id.strip():
        raise AuthorityPolicyError("tenant_id must be normalized")
    if not isinstance(revoked, bool):
        raise AuthorityPolicyError("revoked must be boolean")

    return AuthorityPrincipal(
        principal_id=authority.agent_id,
        kind=PrincipalKind.AGENT,
        tenant_id=tenant_id,
        generation=authority.generation,
        capabilities=authority.capabilities,
        scopes=authority.scopes,
        expires_at=authority.expires_at,
        revoked=revoked,
    )


__all__ = ["principal_from_agent_delegation"]
