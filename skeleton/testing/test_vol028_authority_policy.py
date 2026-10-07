from __future__ import annotations

import hashlib

import pytest

from skeleton.automation.agents.authority_policy_bridge import (
    principal_from_agent_delegation,
)
from skeleton.automation.agents.delegation_qualification import (
    AgentDelegationAuthority,
    DelegationBudget,
)
from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.vault.authority_policy import (
    AuthorityPolicyError,
    AuthorityPrincipal,
    AuthorityRequest,
    PolicyDecision,
    PrincipalKind,
    compile_authority_policy,
    evaluate_authority,
)


BASE_POLICY = """policy core-auth version 7 default deny
allow user-read user repo.read repo:a approval none
allow service-read service repo.read repo:a approval none
allow agent-read agent repo.read repo:a approval none
allow user-write user repo.write repo:a approval required
deny agent-write agent repo.write repo:a
"""


def principal(kind: PrincipalKind, *, revoked: bool = False) -> AuthorityPrincipal:
    capabilities = ("repo.read", "repo.write")
    scopes = ("repo:a",)
    return AuthorityPrincipal(
        principal_id=f"{kind.value}-1",
        kind=kind,
        tenant_id="tenant-a",
        generation=3,
        capabilities=capabilities,
        scopes=scopes,
        expires_at=500.0,
        revoked=revoked,
    )


def request(
    kind: PrincipalKind,
    *,
    capability: str = "repo.read",
    scope: str = "repo:a",
    tenant: str = "tenant-a",
    generation: int = 3,
) -> AuthorityRequest:
    return AuthorityRequest(
        principal_id=f"{kind.value}-1",
        tenant_id=tenant,
        capability=capability,
        scope=scope,
        operation_id="op-1",
        requested_generation=generation,
    )


@pytest.mark.parametrize(
    "kind",
    [PrincipalKind.USER, PrincipalKind.SERVICE, PrincipalKind.AGENT],
)
def test_user_service_and_agent_use_one_evaluator(kind: PrincipalKind) -> None:
    policy = compile_authority_policy(BASE_POLICY)

    decision = evaluate_authority(
        policy=policy,
        principal=principal(kind),
        request=request(kind),
        observed_at=100.0,
    )

    assert decision.allowed is True
    assert decision.reasons == ()
    assert decision.authority_scope == "authority-decision-only"
    assert decision.production_authority is False


def test_policy_is_deny_by_default() -> None:
    policy = compile_authority_policy(BASE_POLICY)
    p = AuthorityPrincipal(
        principal_id="service-1",
        kind=PrincipalKind.SERVICE,
        tenant_id="tenant-a",
        generation=3,
        capabilities=("repo.delete",),
        scopes=("repo:a",),
        expires_at=500.0,
    )
    r = AuthorityRequest(
        principal_id="service-1",
        tenant_id="tenant-a",
        capability="repo.delete",
        scope="repo:a",
        operation_id="op-delete",
        requested_generation=3,
    )

    decision = evaluate_authority(
        policy=policy,
        principal=p,
        request=r,
        observed_at=100.0,
    )

    assert decision.allowed is False
    assert "default-deny" in decision.reasons


def test_explicit_deny_overrides_matching_allow() -> None:
    policy = compile_authority_policy(
        """policy deny-precedence version 1 default deny
allow agent-write agent repo.write repo:a approval none
deny no-agent-write agent repo.write repo:a
"""
    )

    decision = evaluate_authority(
        policy=policy,
        principal=principal(PrincipalKind.AGENT),
        request=request(PrincipalKind.AGENT, capability="repo.write"),
        observed_at=100.0,
    )

    assert decision.allowed is False
    assert "explicit-deny" in decision.reasons
    assert decision.matched_rule_ids == ("agent-write", "no-agent-write")


def test_policy_cannot_widen_principal_capability() -> None:
    policy = compile_authority_policy(BASE_POLICY)
    p = AuthorityPrincipal(
        principal_id="user-1",
        kind=PrincipalKind.USER,
        tenant_id="tenant-a",
        generation=3,
        capabilities=("repo.read",),
        scopes=("repo:a",),
        expires_at=500.0,
    )

    decision = evaluate_authority(
        policy=policy,
        principal=p,
        request=request(PrincipalKind.USER, capability="repo.write"),
        observed_at=100.0,
        approval_ref="approval://operator/123",
    )

    assert decision.allowed is False
    assert "principal-capability-not-granted" in decision.reasons


def test_policy_cannot_widen_principal_scope() -> None:
    policy = compile_authority_policy(
        """policy scope-test version 1 default deny
allow svc service repo.read repo:b approval none
"""
    )
    p = AuthorityPrincipal(
        principal_id="service-1",
        kind=PrincipalKind.SERVICE,
        tenant_id="tenant-a",
        generation=3,
        capabilities=("repo.read",),
        scopes=("repo:a",),
        expires_at=500.0,
    )
    r = AuthorityRequest(
        principal_id="service-1",
        tenant_id="tenant-a",
        capability="repo.read",
        scope="repo:b",
        operation_id="op-1",
        requested_generation=3,
    )

    decision = evaluate_authority(
        policy=policy,
        principal=p,
        request=r,
        observed_at=100.0,
    )

    assert decision.allowed is False
    assert "principal-scope-not-granted" in decision.reasons


def test_tenant_and_generation_are_exactly_bound() -> None:
    policy = compile_authority_policy(BASE_POLICY)

    cross_tenant = evaluate_authority(
        policy=policy,
        principal=principal(PrincipalKind.USER),
        request=request(PrincipalKind.USER, tenant="tenant-b"),
        observed_at=100.0,
    )
    stale_generation = evaluate_authority(
        policy=policy,
        principal=principal(PrincipalKind.USER),
        request=request(PrincipalKind.USER, generation=2),
        observed_at=100.0,
    )

    assert "tenant-boundary-mismatch" in cross_tenant.reasons
    assert "authority-generation-mismatch" in stale_generation.reasons


def test_revoked_and_expired_principals_fail_closed() -> None:
    policy = compile_authority_policy(BASE_POLICY)

    revoked = evaluate_authority(
        policy=policy,
        principal=principal(PrincipalKind.USER, revoked=True),
        request=request(PrincipalKind.USER),
        observed_at=100.0,
    )
    expired = evaluate_authority(
        policy=policy,
        principal=principal(PrincipalKind.USER),
        request=request(PrincipalKind.USER),
        observed_at=500.0,
    )

    assert revoked.allowed is False
    assert "principal-revoked" in revoked.reasons
    assert expired.allowed is False
    assert "principal-expired" in expired.reasons


def test_approval_requirement_is_bound_to_request_and_policy() -> None:
    policy = compile_authority_policy(BASE_POLICY)

    missing = evaluate_authority(
        policy=policy,
        principal=principal(PrincipalKind.USER),
        request=request(PrincipalKind.USER, capability="repo.write"),
        observed_at=100.0,
    )
    approved = evaluate_authority(
        policy=policy,
        principal=principal(PrincipalKind.USER),
        request=request(PrincipalKind.USER, capability="repo.write"),
        observed_at=100.0,
        approval_ref="approval://operator/123",
    )

    assert missing.allowed is False
    assert "approval-required" in missing.reasons
    assert approved.allowed is True
    assert approved.approval_required is True
    assert approved.approval_ref_digest is not None


def test_policy_and_decision_identity_use_shared_canonical_bytes() -> None:
    policy = compile_authority_policy(BASE_POLICY)
    decision = evaluate_authority(
        policy=policy,
        principal=principal(PrincipalKind.SERVICE),
        request=request(PrincipalKind.SERVICE),
        observed_at=100.0,
    )

    assert policy.policy_digest == hashlib.sha256(
        canonical_json_bytes(policy.payload())
    ).hexdigest()
    assert decision.decision_digest == hashlib.sha256(
        canonical_json_bytes(decision.payload())
    ).hexdigest()


@pytest.mark.parametrize(
    "source",
    [
        "policy bad version 1 default allow\nallow r user repo.read repo:a approval none\n",
        "policy bad version 0 default deny\nallow r user repo.read repo:a approval none\n",
        "policy bad version 1 default deny\nallow r user repo.* repo:a approval none\n",
        "policy bad version 1 default deny\nallow r unknown repo.read repo:a approval none\n",
        "policy bad version 1 default deny\nallow r user repo.read repo:a approval maybe\n",
        "policy bad version 1 default deny\n",
    ],
)
def test_invalid_or_broad_policy_source_fails_closed(source: str) -> None:
    with pytest.raises(AuthorityPolicyError):
        compile_authority_policy(source)


def test_duplicate_semantic_rule_is_rejected() -> None:
    with pytest.raises(AuthorityPolicyError, match="duplicate semantic"):
        compile_authority_policy(
            """policy duplicates version 1 default deny
allow a user repo.read repo:a approval none
allow b user repo.read repo:a approval none
"""
        )


def test_authority_decision_cannot_be_forged_into_execution_authority() -> None:
    policy = compile_authority_policy(BASE_POLICY)
    decision = evaluate_authority(
        policy=policy,
        principal=principal(PrincipalKind.USER),
        request=request(PrincipalKind.USER),
        observed_at=100.0,
    )

    with pytest.raises(AuthorityPolicyError, match="authority scope escalation"):
        PolicyDecision(
            allowed=decision.allowed,
            reasons=decision.reasons,
            policy_id=decision.policy_id,
            policy_version=decision.policy_version,
            policy_digest=decision.policy_digest,
            principal_digest=decision.principal_digest,
            request_digest=decision.request_digest,
            matched_rule_ids=decision.matched_rule_ids,
            approval_required=decision.approval_required,
            approval_ref_digest=decision.approval_ref_digest,
            authority_scope="execute-tools",
        )


def test_policy_compiler_is_deterministic_for_same_source() -> None:
    first = compile_authority_policy(BASE_POLICY)
    second = compile_authority_policy(BASE_POLICY)

    assert first == second
    assert first.policy_digest == second.policy_digest
    assert first.source_digest == second.source_digest


def test_authority_policy_source_and_ai_mirror_are_byte_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton/vault/authority_policy.py"
    mirror = root / "skeleton/ai/runtime/vault/authority_policy.py"
    assert source.read_bytes() == mirror.read_bytes()


def test_vault_exports_source_and_ai_mirror_remain_byte_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton/vault/__init__.py"
    mirror = root / "skeleton/ai/runtime/vault/__init__.py"
    assert source.read_bytes() == mirror.read_bytes()


def test_existing_agent_delegation_projects_losslessly_into_unified_policy() -> None:
    authority = AgentDelegationAuthority(
        agent_id="agent-1",
        parent_agent_id="supervisor-1",
        generation=3,
        capabilities=("repo.read", "repo.write"),
        scopes=("repo:a",),
        budget=DelegationBudget(
            max_parallel_tasks=2,
            max_steps=20,
            max_tokens=10000,
            max_cost_units=5.0,
            max_wall_time_s=60.0,
        ),
        expires_at=500.0,
        delegation_id="delegation-3",
    )
    projected = principal_from_agent_delegation(
        authority,
        tenant_id="tenant-a",
    )

    assert projected.kind is PrincipalKind.AGENT
    assert projected.principal_id == authority.agent_id
    assert projected.generation == authority.generation
    assert projected.capabilities == authority.capabilities
    assert projected.scopes == authority.scopes
    assert projected.expires_at == authority.expires_at

    policy = compile_authority_policy(BASE_POLICY)
    decision = evaluate_authority(
        policy=policy,
        principal=projected,
        request=AuthorityRequest(
            principal_id="agent-1",
            tenant_id="tenant-a",
            capability="repo.read",
            scope="repo:a",
            operation_id="op-agent",
            requested_generation=3,
        ),
        observed_at=100.0,
    )
    assert decision.allowed is True


def test_agent_bridge_cannot_unrevoke_or_expand_delegated_authority() -> None:
    authority = AgentDelegationAuthority(
        agent_id="agent-1",
        parent_agent_id="supervisor-1",
        generation=4,
        capabilities=("repo.read",),
        scopes=("repo:a",),
        budget=DelegationBudget(
            max_parallel_tasks=1,
            max_steps=10,
            max_tokens=1000,
            max_cost_units=1.0,
            max_wall_time_s=30.0,
        ),
        expires_at=250.0,
        delegation_id="delegation-4",
    )
    projected = principal_from_agent_delegation(
        authority,
        tenant_id="tenant-a",
        revoked=True,
    )

    assert projected.revoked is True
    assert projected.capabilities == ("repo.read",)
    assert projected.scopes == ("repo:a",)
    assert projected.generation == 4


def test_agent_authority_bridge_source_and_ai_mirror_are_byte_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton/automation/agents/authority_policy_bridge.py"
    mirror = root / "skeleton/ai/agents/core/authority_policy_bridge.py"
    assert source.read_bytes() == mirror.read_bytes()
