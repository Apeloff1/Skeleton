from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from skeleton.ai.runtime.product.learning import (
    CanonicalLearningHandoffError,
    build_learning_candidate,
    build_learning_candidate_artifact,
)
from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
)


NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


def _turn(
    *,
    sequence: int = 1,
    data_class: str = "internal",
    tool_receipts: tuple[str, ...] = (),
) -> tuple[ConversationMessage, ConversationMessage]:
    thread_id = str(uuid4())
    branch_id = str(uuid4())
    user_id = str(uuid4())
    assistant_id = str(uuid4())
    operation_id = str(uuid4())
    context_id = str(uuid4())
    context_digest = "a" * 64

    user = ConversationMessage(
        message_id=user_id,
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=sequence,
        author_type=ConversationAuthorType.USER,
        created_at=NOW,
        idempotency_key=f"turn-{sequence}",
        content="What is the safest deterministic answer?",
        data_class=data_class,
    )
    assistant = ConversationMessage(
        message_id=assistant_id,
        thread_id=thread_id,
        branch_id=branch_id,
        sequence=sequence + 1,
        author_type=ConversationAuthorType.ASSISTANT,
        created_at=NOW,
        idempotency_key=f"turn-{sequence}:assistant",
        content="Use the verified deterministic path.",
        parent_message_id=user_id,
        causal_user_message_id=user_id,
        operation_id=operation_id,
        ai_result_id="ai-result:" + ("b" * 32),
        context_id=context_id,
        context_digest=context_digest,
        context_source_snapshot=((str(uuid4()), "c" * 64),),
        context_compiler_version="test-compiler-v1",
        provider_receipt_refs=("provider-receipt:test",),
        tool_receipt_refs=tool_receipts,
        data_class=data_class,
    )
    return user, assistant


def test_learning_handoff_requires_explicit_acceptance() -> None:
    user, assistant = _turn()
    with pytest.raises(
        CanonicalLearningHandoffError,
        match="explicit accepted",
    ):
        build_learning_candidate(
            (user, assistant),
            accepted_assistant_message_ids=(),
        )


def test_learning_handoff_binds_only_explicit_accepted_lineage() -> None:
    user, assistant = _turn()
    candidate = build_learning_candidate(
        (user, assistant),
        accepted_assistant_message_ids=(assistant.message_id,),
    )

    assert len(candidate.pairs) == 1
    pair = candidate.pairs[0]
    assert pair.user_message_id == user.message_id
    assert pair.assistant_message_id == assistant.message_id
    assert pair.operation_id == assistant.operation_id
    assert pair.ai_result_id == assistant.ai_result_id
    assert pair.context_id == assistant.context_id
    assert pair.context_digest == assistant.context_digest
    assert pair.provider_receipt_refs == assistant.provider_receipt_refs
    assert candidate.reference.startswith("product-learning-sha256:")
    assert candidate.documents == (
        "<|user|>\nWhat is the safest deterministic answer?"
        "\n<|assistant|>\nUse the verified deterministic path.",
    )


def test_learning_candidate_identity_is_deterministic() -> None:
    user, assistant = _turn()
    first = build_learning_candidate(
        (user, assistant),
        accepted_assistant_message_ids=(assistant.message_id,),
    )
    second = build_learning_candidate(
        (user, assistant),
        accepted_assistant_message_ids=(assistant.message_id,),
    )
    assert first.identity_digest == second.identity_digest
    assert first.as_dict() == second.as_dict()


def test_learning_handoff_rejects_private_class_by_default() -> None:
    user, assistant = _turn(data_class="confidential")
    with pytest.raises(
        CanonicalLearningHandoffError,
        match="data class is not admitted",
    ):
        build_learning_candidate(
            (user, assistant),
            accepted_assistant_message_ids=(assistant.message_id,),
        )

    candidate = build_learning_candidate(
        (user, assistant),
        accepted_assistant_message_ids=(assistant.message_id,),
        allowed_data_classes=("confidential",),
    )
    assert candidate.pairs[0].data_class == "confidential"


def test_tool_augmented_turn_requires_separate_opt_in() -> None:
    user, assistant = _turn(
        tool_receipts=("tool-receipt:read-only-evidence",)
    )
    with pytest.raises(
        CanonicalLearningHandoffError,
        match="tool-augmented",
    ):
        build_learning_candidate(
            (user, assistant),
            accepted_assistant_message_ids=(assistant.message_id,),
        )

    candidate = build_learning_candidate(
        (user, assistant),
        accepted_assistant_message_ids=(assistant.message_id,),
        allow_tool_augmented=True,
    )
    assert candidate.tool_augmented is True
    assert candidate.pairs[0].tool_receipt_refs


def test_learning_handoff_rejects_lineage_breaks() -> None:
    user, assistant = _turn()
    wrong_parent = ConversationMessage(
        **{
            **assistant.as_dict(),
            "author_type": ConversationAuthorType.ASSISTANT,
            "created_at": NOW,
            "context_source_snapshot": tuple(
                tuple(item)
                for item in assistant.as_dict()["context_source_snapshot"]
            ),
            "parent_message_id": str(uuid4()),
        }
    )
    with pytest.raises(
        CanonicalLearningHandoffError,
        match="directly parented",
    ):
        build_learning_candidate(
            (user, wrong_parent),
            accepted_assistant_message_ids=(wrong_parent.message_id,),
        )


def test_learning_handoff_rejects_content_ref_only_examples() -> None:
    user, assistant = _turn()
    content_ref_assistant = ConversationMessage(
        message_id=assistant.message_id,
        thread_id=assistant.thread_id,
        branch_id=assistant.branch_id,
        sequence=assistant.sequence,
        author_type=assistant.author_type,
        created_at=assistant.created_at,
        idempotency_key=assistant.idempotency_key,
        content_ref="blob:assistant-content",
        parent_message_id=assistant.parent_message_id,
        causal_user_message_id=assistant.causal_user_message_id,
        operation_id=assistant.operation_id,
        ai_result_id=assistant.ai_result_id,
        context_id=assistant.context_id,
        context_digest=assistant.context_digest,
        context_source_snapshot=assistant.context_source_snapshot,
        context_compiler_version=assistant.context_compiler_version,
        provider_receipt_refs=assistant.provider_receipt_refs,
        data_class=assistant.data_class,
    )
    with pytest.raises(
        CanonicalLearningHandoffError,
        match="materialization",
    ):
        build_learning_candidate(
            (user, content_ref_assistant),
            accepted_assistant_message_ids=(content_ref_assistant.message_id,),
        )


def test_candidate_artifact_cannot_overwrite_active_model(
    tmp_path: Path,
    monkeypatch,
) -> None:
    user, assistant = _turn()
    candidate = build_learning_candidate(
        (user, assistant),
        accepted_assistant_message_ids=(assistant.message_id,),
    )
    active = tmp_path / "active.json"
    monkeypatch.setenv("AI_LOCAL_MODEL_PATH", str(active))

    with pytest.raises(
        CanonicalLearningHandoffError,
        match="cannot overwrite active",
    ):
        build_learning_candidate_artifact(
            candidate,
            output_path=active,
            model_id="unsafe-replacement",
            hidden_size=8,
            epochs=1,
            max_vocab=32,
            max_document_tokens=64,
        )


def test_candidate_artifact_is_trainable_but_remains_unpromoted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pytest.importorskip("numpy")
    user, assistant = _turn()
    candidate = build_learning_candidate(
        (user, assistant),
        accepted_assistant_message_ids=(assistant.message_id,),
    )
    monkeypatch.delenv("AI_LOCAL_MODEL_PATH", raising=False)
    output = tmp_path / "candidate.json"

    receipt = build_learning_candidate_artifact(
        candidate,
        output_path=output,
        model_id="reverse-learning-candidate",
        hidden_size=8,
        epochs=1,
        learning_rate=0.03,
        max_vocab=32,
        max_document_tokens=64,
        seed=17,
        temperature=0.7,
    )

    assert output.is_file()
    assert receipt["model_id"] == "reverse-learning-candidate"
    assert receipt["learning_candidate_ref"] == candidate.reference
    assert receipt["learning_candidate_digest"] == candidate.identity_digest
    assert receipt["learning_pair_count"] == 1
    assert receipt["promotion_state"] == "candidate_only"
