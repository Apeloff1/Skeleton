from __future__ import annotations

from datetime import datetime, timezone

import pytest

from skeleton.context.instruction_policy import (
    INSTRUCTION_POLICIES,
    InstructionPolicy,
    InstructionPolicyError,
    InstructionPolicyRegistry,
    build_default_instruction_policy_registry,
)
from skeleton.contracts.context import ContextKind, ContextTrust


def _now():
    return datetime(2026, 9, 23, 20, 30, tzinfo=timezone.utc)


def test_policy_digest_is_stable_and_content_sensitive() -> None:
    first = InstructionPolicy(
        policy_id="test.policy",
        version="1.0.0",
        content="Stable trusted instruction.",
        provenance="tests",
    )
    replay = InstructionPolicy(
        policy_id="test.policy",
        version="1.0.0",
        content="Stable trusted instruction.",
        provenance="tests",
    )
    changed = InstructionPolicy(
        policy_id="test.policy",
        version="1.0.0",
        content="Different trusted instruction.",
        provenance="tests",
    )

    assert first.digest == replay.digest
    assert first.identity == replay.identity
    assert first.digest != changed.digest


def test_registry_rejects_same_version_with_different_content() -> None:
    registry = InstructionPolicyRegistry()
    registry.register(
        InstructionPolicy(
            policy_id="test.policy",
            version="1.0.0",
            content="v1",
            provenance="tests",
        ),
        activate=True,
    )

    with pytest.raises(InstructionPolicyError, match="different content"):
        registry.register(
            InstructionPolicy(
                policy_id="test.policy",
                version="1.0.0",
                content="mutated",
                provenance="tests",
            )
        )


def test_explicit_activation_and_rollback_preserve_registered_digests() -> None:
    registry = InstructionPolicyRegistry()
    v1 = registry.register(
        InstructionPolicy(
            policy_id="test.policy",
            version="1.0.0",
            content="first",
            provenance="tests/v1",
        ),
        activate=True,
    )
    v2 = registry.register(
        InstructionPolicy(
            policy_id="test.policy",
            version="2.0.0",
            content="second",
            provenance="tests/v2",
        )
    )

    assert registry.resolve("test.policy") == v1
    registry.activate("test.policy", "2.0.0")
    assert registry.resolve("test.policy") == v2
    assert registry.active_version("test.policy") == "2.0.0"

    rolled_back = registry.rollback("test.policy", "1.0.0")

    assert rolled_back == v1
    assert registry.resolve("test.policy").digest == v1.digest
    assert registry.resolve("test.policy").digest != v2.digest


def test_policy_segment_is_mandatory_trusted_control_with_digest_lineage() -> None:
    policy = INSTRUCTION_POLICIES.resolve("chat.jeeves")

    segment = policy.as_segment(
        tenant_id="tenant-a",
        purpose="chat",
        created_at=_now(),
    )

    assert segment.kind is ContextKind.PRODUCT_INSTRUCTION
    assert segment.trust_level is ContextTrust.TRUSTED_CONTROL
    assert segment.source_type == "product-policy"
    assert segment.mandatory is True
    assert "instruction-policy-digest:" + policy.digest in segment.provenance


def test_default_registry_contains_all_required_product_policy_ids() -> None:
    registry = build_default_instruction_policy_registry()
    required = {
        "code.explain",
        "code.debug",
        "code.optimize",
        "code.complete",
        "code.refactor",
        "code.document",
        "code.test_gen",
        "code.security_audit",
        "code.convert",
        "code.review",
        "code.teach",
        "code.architecture",
        "chat.jeeves",
        "image.prompt_enhance",
    }

    assert {row["policy_id"] for row in registry.snapshot()} == required
    assert all(row["active"] == "true" for row in registry.snapshot())


def test_convert_and_image_policies_keep_user_values_out_of_trusted_text() -> None:
    convert = INSTRUCTION_POLICIES.resolve("code.convert")
    image = INSTRUCTION_POLICIES.resolve("image.prompt_enhance")

    assert "{target_language}" not in convert.content
    assert "Python" not in convert.content
    assert "target language named in the user request" in convert.content
    assert "Treat the original prompt" in image.content
    assert "user data" in image.content
    assert "change your role" in image.content
