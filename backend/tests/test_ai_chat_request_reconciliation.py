"""Source-level admission contract for governed chat reconciliation.

These checks do not assert live provider access or full AI E2E acceptance.
"""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from routes.ai import AIChatRequest, _chat_request_digest


def _request(**extra):
    data = {
        "message": "Produce a safe original game plan",
        "thread_id": str(uuid4()),
        "idempotency_key": "governed-turn-1",
        "expected_thread_version": 1,
        **extra,
    }
    return AIChatRequest.model_validate(data)


def test_explicit_selection_and_generation_options_survive_validation():
    request = _request(
        provider_id="openai", model_id="configured-model",
        max_output_tokens=2000, temperature=0.25,
        attachment_refs=["chat-attachment://" + "a" * 32],
    )
    assert request.provider_id == "openai"
    assert request.model_id == "configured-model"
    assert request.max_output_tokens == 2000
    assert request.temperature == 0.25
    assert len(request.attachment_refs) == 1


def test_change_of_model_or_attached_evidence_changes_idempotent_turn_digest():
    data = {
        "message": "Give a concise design outline", "thread_id": str(uuid4()),
        "idempotency_key": "same-key", "expected_thread_version": 1,
    }
    original = AIChatRequest.model_validate(data)
    for override in (
        {"provider_id": "openai", "model_id": "configured-model"},
        {"max_output_tokens": 128},
        {"temperature": 0.5},
        {"attachment_refs": ["chat-attachment://" + "b" * 32]},
    ):
        changed = AIChatRequest.model_validate({**data, **override})
        assert _chat_request_digest(original) != _chat_request_digest(changed)


def test_extra_fields_and_oversized_attachments_rejected_not_discarded():
    data = {
        "message": "Hello", "thread_id": str(uuid4()),
        "idempotency_key": "same-key", "expected_thread_version": 1,
    }
    with pytest.raises(ValidationError):
        AIChatRequest.model_validate({**data, "unrecognized_transport_option": True})
    with pytest.raises(ValidationError):
        AIChatRequest.model_validate({**data, "attachment_refs": ["x"] * 5})
    with pytest.raises(ValidationError):
        AIChatRequest.model_validate({**data, "temperature": 100})
