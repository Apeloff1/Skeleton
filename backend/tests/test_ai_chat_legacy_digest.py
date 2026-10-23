"""Bind legacy chat request identities without relaxing replay semantics."""

from __future__ import annotations

import hashlib
import json

import pytest

from routes.ai import AIChatRequest, _chat_request_digest_candidates


def _request(**changes) -> AIChatRequest:
    data = {
        "message": "historical request",
        "thread_id": "historical-thread",
        "idempotency_key": "request-1",
        "expected_thread_version": 1,
    }
    data.update(changes)
    return AIChatRequest(**data)


def _original_digest(request: AIChatRequest) -> str:
    payload = {
        "schema_version": "backend.ai.chat-request.v1",
        "message": request.message,
        "idempotency_key": request.idempotency_key,
        "context_sha256": (
            hashlib.sha256(request.context.encode("utf-8")).hexdigest()
            if request.context is not None else None
        ),
        "memory_policy": (
            request.memory_policy.model_dump(mode="json")
            if request.memory_policy is not None else None
        ),
    }
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def test_oldest_v1_request_digest_is_recognized_for_true_legacy_replay():
    request = _request()
    assert _original_digest(request) in _chat_request_digest_candidates(request)


def test_original_v1_digest_binds_ephemeral_context_exactly():
    request = _request(context="approved context")
    assert _original_digest(request) in _chat_request_digest_candidates(request)
    changed = request.model_copy(update={"context": "unapproved context"})
    assert _original_digest(request) not in _chat_request_digest_candidates(changed)


@pytest.mark.parametrize(
    "changes",
    [
        {"attachment_refs": ("asset:abc",)},
        {"provider_id": "local", "model_id": "model-a"},
        {"max_output_tokens": 256},
        {"temperature": 0.5},
        {"crawler_context": {"query": "public information"}},
        {"cooperation": {"schema_version": "skeleton.ai.cooperation.v1", "roles": {"draft": {"provider_id": "local", "model_id": "model-a"}}}},
        {"memory_references": [{"memory_id": "prior-memory"}]},
    ],
)
def test_original_v1_digest_cannot_alias_new_execution_semantics(changes):
    baseline = _request()
    enhanced = _request(**changes)
    assert _original_digest(baseline) not in _chat_request_digest_candidates(enhanced)


def test_legacy_replay_does_not_ignore_content_or_idempotency_changes():
    original = _request()
    for revised in (
        original.model_copy(update={"message": "different"}),
        original.model_copy(update={"idempotency_key": "different"}),
    ):
        assert _original_digest(original) not in _chat_request_digest_candidates(revised)
