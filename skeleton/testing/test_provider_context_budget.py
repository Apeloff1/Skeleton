from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from skeleton.contracts.context import (
    ContextBudget,
    ContextKind,
    ContextSegment,
    ContextTrust,
)
from skeleton.context.compiler import ContextCompiler
from skeleton.provider_runtime import (
    ProviderPolicyError,
    provider_request_from_context,
)


NOW = datetime(2026, 9, 26, 0, 0, tzinfo=timezone.utc)


def _segment(
    content: str,
    *,
    kind: ContextKind,
    trust: ContextTrust,
    source_id: str,
    mandatory: bool = False,
) -> ContextSegment:
    return ContextSegment.from_content(
        segment_id=str(uuid4()),
        kind=kind,
        source_type="test",
        source_id=source_id,
        content=content,
        trust_level=trust,
        data_class="internal",
        tenant_id="tenant-a",
        purpose="model-inference",
        priority=1000 if mandatory else 500,
        relevance=1.0,
        created_at=NOW,
        provenance=("test:provider-context-budget",),
        retention_class="test",
        mandatory=mandatory,
    )


def _envelope():
    budget = ContextBudget(
        max_context_tokens=4096,
        reserved_output_tokens=512,
        reserved_tool_result_tokens=256,
        reserved_policy_tokens=256,
        safety_margin_tokens=128,
        max_segment_tokens=2048,
        max_artifact_tokens=1024,
        max_tool_result_tokens=1024,
    )
    segments = (
        _segment(
            "Follow the canonical instruction.",
            kind=ContextKind.PRODUCT_INSTRUCTION,
            trust=ContextTrust.TRUSTED_CONTROL,
            source_id="policy",
            mandatory=True,
        ),
        _segment(
            "Explain the bounded provider request.",
            kind=ContextKind.USER_MESSAGE,
            trust=ContextTrust.USER_AUTHORED,
            source_id="user-message",
        ),
    )
    return ContextCompiler().compile(
        operation_id=str(uuid4()),
        execution_id=str(uuid4()),
        turn_id=str(uuid4()),
        tenant_id="tenant-a",
        purpose="model-inference",
        budget=budget,
        segments=segments,
        tools_enabled=False,
        compiled_at=NOW,
    )


def test_provider_request_inherits_compiler_input_and_output_bounds() -> None:
    envelope = _envelope()

    request = provider_request_from_context(envelope)

    assert request.resource_budget.max_input_tokens == (
        envelope.budget.input_capacity(tools_enabled=False)
    )
    assert request.resource_budget.max_output_tokens == (
        envelope.budget.reserved_output_tokens
    )
    assert request.max_output_tokens == envelope.budget.reserved_output_tokens
    assert envelope.selected_tokens_estimate <= (
        request.resource_budget.max_input_tokens
    )


def test_provider_request_rejects_output_above_compiler_reserve() -> None:
    envelope = _envelope()

    with pytest.raises(
        ProviderPolicyError,
        match="exceeds context output reservation",
    ):
        provider_request_from_context(
            envelope,
            max_output_tokens=envelope.budget.reserved_output_tokens + 1,
        )


def test_provider_request_allows_smaller_output_with_same_input_ceiling() -> None:
    envelope = _envelope()

    request = provider_request_from_context(
        envelope,
        max_output_tokens=128,
    )

    assert request.max_output_tokens == 128
    assert request.resource_budget.max_input_tokens == (
        envelope.budget.input_capacity(tools_enabled=False)
    )
