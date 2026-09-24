from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from skeleton.contracts.context import ContextBudget, ContextKind, ContextSegment, ContextTrust
from skeleton.context.compiler import ContextCompiler
from skeleton.provider_runtime import (
    FinishReason,
    ProviderPolicyError,
    ProviderResponse,
    require_provider_response_context,
)


NOW = datetime(2026, 9, 24, 2, 30, tzinfo=timezone.utc)


def _envelope():
    segment = ContextSegment.from_content(
        segment_id=str(uuid4()),
        kind=ContextKind.USER_MESSAGE,
        source_type="conversation",
        source_id="user-message",
        content="hello",
        trust_level=ContextTrust.AUTHORIZED_USER_DATA,
        data_class="internal",
        tenant_id="tenant-a",
        purpose="model-inference",
        priority=800,
        relevance=1.0,
        created_at=NOW,
        provenance=("conversation:test",),
        retention_class="conversation",
    )
    return ContextCompiler().compile(
        operation_id=str(uuid4()),
        execution_id=str(uuid4()),
        turn_id=str(uuid4()),
        tenant_id="tenant-a",
        purpose="model-inference",
        budget=ContextBudget(
            max_context_tokens=200,
            reserved_output_tokens=20,
            reserved_tool_result_tokens=0,
            reserved_policy_tokens=20,
            safety_margin_tokens=10,
            max_segment_tokens=100,
            max_artifact_tokens=80,
            max_tool_result_tokens=80,
        ),
        segments=(segment,),
        compiled_at=NOW,
    )


def _response(envelope, **overrides):
    values = {
        "text": "ok",
        "provider": "test",
        "model": "test",
        "finish_reason": FinishReason.STOP,
        "context_id": envelope.context_id,
        "context_digest": envelope.context_digest,
        "context_source_snapshot": envelope.source_snapshot,
        "context_compiler_version": envelope.compiler_version,
    }
    values.update(overrides)
    return ProviderResponse(**values)


def test_provider_response_must_match_exact_compiled_context():
    envelope = _envelope()
    response = _response(envelope)
    assert require_provider_response_context(response, envelope) is response

    with pytest.raises(ProviderPolicyError, match="digest mismatch"):
        require_provider_response_context(
            _response(envelope, context_digest="0" * 64),
            envelope,
        )

    with pytest.raises(ProviderPolicyError, match="snapshot mismatch"):
        require_provider_response_context(
            _response(envelope, context_source_snapshot=()),
            envelope,
        )


def test_context_binding_dict_carries_turn_and_source_identity():
    envelope = _envelope()
    binding = envelope.binding_dict()
    assert binding["context_id"] == envelope.context_id
    assert binding["context_digest"] == envelope.context_digest
    assert binding["turn_id"] == envelope.turn_id
    assert binding["source_snapshot"] == [
        list(item) for item in envelope.source_snapshot
    ]
