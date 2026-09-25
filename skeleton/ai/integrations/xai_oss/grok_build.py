"""Deterministic Grok-Build-derived control primitives.

These are clean-room compatibility primitives, not imports from the research
snapshot. Skeleton remains the authority for tool admission and durable state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from pathlib import Path
from typing import Iterable, Mapping, Sequence


class ToolApprovalPolicy(str, Enum):
    ALWAYS_PROMPT = "always_prompt"
    GRANTS_ALLOWED = "grants_allowed"
    UNATTENDED_ALLOWED = "unattended_allowed"


class ToolEffect(str, Enum):
    READ = "read"
    SEARCH = "search"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK_FETCH = "network_fetch"
    MCP = "mcp"
    AGENT_MESSAGE = "agent_message"


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    requires_approval: bool
    reason_code: str


def approval_for_effect(
    effect: ToolEffect,
    *,
    policy: ToolApprovalPolicy = ToolApprovalPolicy.GRANTS_ALLOWED,
    persisted_grant: bool = False,
    unattended_session: bool = False,
) -> ApprovalDecision:
    effect = effect if isinstance(effect, ToolEffect) else ToolEffect(str(effect))
    policy = (
        policy
        if isinstance(policy, ToolApprovalPolicy)
        else ToolApprovalPolicy(str(policy))
    )
    if effect in {ToolEffect.READ, ToolEffect.SEARCH}:
        return ApprovalDecision(False, "read-or-search")
    if policy is ToolApprovalPolicy.ALWAYS_PROMPT:
        return ApprovalDecision(True, "always-prompt")
    if persisted_grant:
        return ApprovalDecision(False, "persisted-grant")
    if (
        policy is ToolApprovalPolicy.UNATTENDED_ALLOWED
        and unattended_session
    ):
        return ApprovalDecision(False, "unattended-authorized")
    return ApprovalDecision(True, "mutation-requires-approval")


class McpTier(str, Enum):
    FIRST_PARTY = "first_party"
    THIRD_PARTY = "third_party"


@dataclass(frozen=True, slots=True)
class McpOffer:
    server_name: str
    tier: McpTier
    tool_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.server_name.strip():
            raise ValueError("server_name must be non-empty")
        if len(set(self.tool_ids)) != len(self.tool_ids):
            raise ValueError("one MCP server may not offer duplicate tool ids")
        if any(not tool_id.strip() for tool_id in self.tool_ids):
            raise ValueError("tool ids must be non-empty")


@dataclass(frozen=True, slots=True)
class McpClaimPlan:
    claims: Mapping[str, tuple[str, ...]]
    rejected: int
    over_cap: int


def plan_mcp_claims(
    offers: Sequence[McpOffer],
    *,
    native_tool_ids: Iterable[str] = (),
    cap: int = 128,
) -> McpClaimPlan:
    if cap < 0:
        raise ValueError("cap must be non-negative")
    native = {str(tool_id) for tool_id in native_tool_ids}
    ordered = sorted(
        offers,
        key=lambda item: (
            0 if item.tier is McpTier.FIRST_PARTY else 1,
            item.server_name,
        ),
    )
    first_counts: dict[str, int] = {}
    third_counts: dict[str, int] = {}
    for offer in ordered:
        counts = first_counts if offer.tier is McpTier.FIRST_PARTY else third_counts
        for tool_id in offer.tool_ids:
            counts[tool_id] = counts.get(tool_id, 0) + 1

    claims: dict[str, tuple[str, ...]] = {}
    rejected = 0
    over_cap = 0
    advertised = 0
    for offer in ordered:
        kept: list[str] = []
        for tool_id in offer.tool_ids:
            claimable = False
            if tool_id not in native:
                if offer.tier is McpTier.FIRST_PARTY:
                    claimable = first_counts.get(tool_id) == 1
                else:
                    claimable = (
                        tool_id not in first_counts
                        and third_counts.get(tool_id) == 1
                    )
            if not claimable:
                rejected += 1
                continue
            if advertised >= cap:
                over_cap += 1
                continue
            advertised += 1
            kept.append(tool_id)
        claims[offer.server_name] = tuple(kept)
    return McpClaimPlan(claims=claims, rejected=rejected, over_cap=over_cap)


def safe_checkpoint_session_name(session_id: str) -> str:
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id must be non-empty")
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def checkpoint_directory(root: Path, session_id: str) -> Path:
    return root / ".grok" / "rewind-checkpoints" / safe_checkpoint_session_name(session_id)


__all__ = [
    "ApprovalDecision",
    "McpClaimPlan",
    "McpOffer",
    "McpTier",
    "ToolApprovalPolicy",
    "ToolEffect",
    "approval_for_effect",
    "checkpoint_directory",
    "plan_mcp_claims",
    "safe_checkpoint_session_name",
]
