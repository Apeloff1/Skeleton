from __future__ import annotations

from pathlib import Path

from skeleton.ai.integrations.xai_oss import (
    McpOffer,
    McpTier,
    ToolApprovalPolicy,
    ToolEffect,
    approval_for_effect,
    checkpoint_directory,
    plan_mcp_claims,
    safe_checkpoint_session_name,
)


def test_mutating_tools_require_approval_by_default() -> None:
    for effect in (
        ToolEffect.WRITE,
        ToolEffect.EXECUTE,
        ToolEffect.NETWORK_FETCH,
        ToolEffect.MCP,
        ToolEffect.AGENT_MESSAGE,
    ):
        decision = approval_for_effect(effect)
        assert decision.requires_approval

    assert not approval_for_effect(ToolEffect.READ).requires_approval
    assert not approval_for_effect(ToolEffect.SEARCH).requires_approval


def test_always_prompt_ignores_persisted_grants() -> None:
    decision = approval_for_effect(
        ToolEffect.WRITE,
        policy=ToolApprovalPolicy.ALWAYS_PROMPT,
        persisted_grant=True,
        unattended_session=True,
    )
    assert decision.requires_approval
    assert decision.reason_code == "always-prompt"


def test_unattended_requires_explicit_unattended_policy_and_session() -> None:
    assert approval_for_effect(
        ToolEffect.EXECUTE,
        policy=ToolApprovalPolicy.UNATTENDED_ALLOWED,
        unattended_session=True,
    ).requires_approval is False
    assert approval_for_effect(
        ToolEffect.EXECUTE,
        policy=ToolApprovalPolicy.GRANTS_ALLOWED,
        unattended_session=True,
    ).requires_approval is True


def test_mcp_first_party_outranks_third_party_and_native_tools() -> None:
    plan = plan_mcp_claims(
        (
            McpOffer("third", "third_party", ("shared", "third-only", "native")),
            McpOffer("first", "first_party", ("shared", "first-only")),
        ),
        native_tool_ids=("native",),
        cap=10,
    )
    assert plan.claims["first"] == ("shared", "first-only")
    assert plan.claims["third"] == ("third-only",)
    assert plan.rejected == 2
    assert plan.over_cap == 0


def test_mcp_same_tier_collision_is_ambiguous_not_order_dependent() -> None:
    plan = plan_mcp_claims(
        (
            McpOffer("b", McpTier.THIRD_PARTY, ("collision",)),
            McpOffer("a", McpTier.THIRD_PARTY, ("collision",)),
        ),
        cap=10,
    )
    assert plan.claims == {"a": (), "b": ()}
    assert plan.rejected == 2


def test_mcp_cap_is_spent_first_party_first() -> None:
    plan = plan_mcp_claims(
        (
            McpOffer("third", McpTier.THIRD_PARTY, ("t1", "t2")),
            McpOffer("first", McpTier.FIRST_PARTY, ("f1", "f2")),
        ),
        cap=2,
    )
    assert plan.claims["first"] == ("f1", "f2")
    assert plan.claims["third"] == ()
    assert plan.over_cap == 2


def test_checkpoint_namespace_never_uses_raw_session_id() -> None:
    session_id = "../../etc/passwd"
    safe = safe_checkpoint_session_name(session_id)
    assert "/" not in safe
    assert "." not in safe
    assert len(safe) == 64

    root = Path("/workspace")
    path = checkpoint_directory(root, session_id)
    assert path.parent.parent == root / ".grok"
    assert path.name == safe
