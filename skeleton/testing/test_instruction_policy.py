from __future__ import annotations

from datetime import datetime, timezone

import pytest

from skeleton.contracts.context import ContextKind, ContextTrust
from skeleton.context.instruction_policy import (
    InstructionPolicy,
    InstructionPolicyError,
    InstructionPolicyRegistry,
)


NOW = datetime(2026, 9, 24, 2, 0, tzinfo=timezone.utc)


def test_instruction_policy_digest_and_segment_identity_are_stable():
    first = InstructionPolicy(
        policy_id="backend.ai.chat",
        version="1",
        instructions="Answer as the canonical coding assistant.",
    )
    second = InstructionPolicy(
        policy_id="backend.ai.chat",
        version="1",
        instructions="Answer as the canonical coding assistant.",
    )
    assert first.digest == second.digest
    assert first.identity == second.identity

    segment = first.to_segment(
        tenant_id="tenant-a",
        purpose="model-inference",
        created_at=NOW,
    )
    assert segment.kind is ContextKind.PRODUCT_INSTRUCTION
    assert segment.trust_level is ContextTrust.TRUSTED_CONTROL
    assert segment.source_id == "backend.ai.chat@1"
    assert "instruction-digest:" + first.digest in segment.provenance


def test_same_policy_version_cannot_be_redefined():
    registry = InstructionPolicyRegistry()
    registry.register(
        InstructionPolicy(
            policy_id="backend.ai.chat",
            version="1",
            instructions="first",
        )
    )
    with pytest.raises(InstructionPolicyError, match="redefined"):
        registry.register(
            InstructionPolicy(
                policy_id="backend.ai.chat",
                version="1",
                instructions="different",
            )
        )


def test_registry_supports_explicit_activation_and_rollback():
    v1 = InstructionPolicy(
        policy_id="backend.ai.chat",
        version="1",
        instructions="v1",
    )
    v2 = InstructionPolicy(
        policy_id="backend.ai.chat",
        version="2",
        instructions="v2",
    )
    registry = InstructionPolicyRegistry((v1, v2))
    assert registry.get("backend.ai.chat") is v1
    assert registry.activate("backend.ai.chat", "2") is v2
    assert registry.get("backend.ai.chat") is v2
    assert registry.rollback("backend.ai.chat", "1") is v1
    assert registry.active_identity("backend.ai.chat") == v1.identity
