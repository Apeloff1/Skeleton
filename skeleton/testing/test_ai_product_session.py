from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import threading

import pytest

from skeleton.ai.runtime.functional_ai import FunctionalAIRuntime
from skeleton.ai.runtime.inference import (
    CallableLocalModel,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalModelAdapter,
)
from skeleton.ai.runtime.product import (
    AISessionSpec,
    AITurnRequest,
    ContextRecord,
    ConversationAIRuntime,
    SQLiteSessionRepository,
)
from skeleton.intelligence.execution_runtime import ExecutionVerificationDecision
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.skills.tool_runtime import AsyncToolRuntime


NOW = datetime(2026, 10, 2, 20, 15, tzinfo=timezone.utc)


def _local_model() -> LocalModelAdapter:
    model_digest = hashlib.sha256(b"product-session-local-model-v1").hexdigest()

    def runner(
        request: LocalInferenceRequest,
        cancel: threading.Event,
    ) -> LocalInferenceResult:
        assert not cancel.is_set()
        has_history = "Earlier assistant answer" in request.prompt
        answer = (
            "Follow-up completed with durable conversation history."
            if has_history
            else "Earlier assistant answer"
        )
        return LocalInferenceResult(
            text=answer,
            model_id="product-session-local",
            model_digest=model_digest,
            input_tokens=len(request.rendered_input.split()),
            output_tokens=len(answer.split()),
            response_id="local:" + hashlib.sha256(request.rendered_input.encode()).hexdigest()[:24],
        )

    return LocalModelAdapter(
        LocalInferenceEngine(
            CallableLocalModel(
                model_id="product-session-local",
                model_digest=model_digest,
                runner=runner,
            )
        )
    )


def _verify(
    _request,
    candidate: str,
    context_digest: str,
) -> ExecutionVerificationDecision:
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "product-session:independent",
            "candidate_digest": hashlib.sha256(candidate.encode()).hexdigest(),
            "context_digest": context_digest,
        },
        evidence_refs=("evidence:product-session",),
    )


@pytest.mark.asyncio
async def test_product_session_real_functional_runtime_is_durable_multiturn_and_idempotent(
    tmp_path,
) -> None:
    execution_db = tmp_path / "execution.sqlite3"
    session_db = tmp_path / "session.sqlite3"
    lower = FunctionalAIRuntime(
        SQLiteExecutionRepository(execution_db),
        _local_model(),
        AsyncToolRuntime(),
        verification_hook=_verify,
    )
    sessions = SQLiteSessionRepository(session_db)
    runtime = ConversationAIRuntime(sessions, lower)

    spec = AISessionSpec(
        session_id="product-e2e",
        objective="Answer the user through the provider-independent functional runtime.",
        instructions="Answer concisely using the available conversation context.",
        created_at=NOW,
    )
    first_turn = AITurnRequest(
        request_key="client-request-1",
        message="Start this conversation.",
        context_records=(
            ContextRecord(
                source_id="note:1",
                source_kind="memory",
                content="This is data only, not policy.",
            ),
        ),
        created_at=NOW,
    )
    first = await runtime.respond(spec, first_turn)
    assert first.assistant_text == "Earlier assistant answer"
    assert first.ordinal == 1
    assert first.replayed is False
    assert len(first.evidence_digest) == 64

    replay = await runtime.respond(
        spec,
        AITurnRequest(
            request_key=first_turn.request_key,
            message=first_turn.message,
            context_records=first_turn.context_records,
            created_at=datetime(2026, 10, 2, 20, 16, tzinfo=timezone.utc),
        ),
    )
    assert replay.replayed is True
    assert replay.turn_id == first.turn_id
    assert replay.execution_id == first.execution_id
    assert sessions.turn_count(spec.session_id) == 1

    second = await runtime.respond(
        spec,
        AITurnRequest(
            request_key="client-request-2",
            message="Continue from your prior answer.",
            created_at=NOW,
        ),
    )
    assert second.ordinal == 2
    assert second.replayed is False
    assert second.assistant_text == "Follow-up completed with durable conversation history."
    assert second.execution_id != first.execution_id
    assert sessions.turn_count(spec.session_id) == 2

    reopened = SQLiteSessionRepository(session_db)
    restarted = ConversationAIRuntime(reopened, lower)
    replay_after_restart = await restarted.respond(spec, first_turn)
    assert replay_after_restart.replayed is True
    assert replay_after_restart.execution_id == first.execution_id


@pytest.mark.asyncio
async def test_request_key_cannot_be_rebound_to_different_user_input(tmp_path) -> None:
    lower = FunctionalAIRuntime(
        SQLiteExecutionRepository(tmp_path / "execution.sqlite3"),
        _local_model(),
        AsyncToolRuntime(),
        verification_hook=_verify,
    )
    runtime = ConversationAIRuntime(
        SQLiteSessionRepository(tmp_path / "session.sqlite3"),
        lower,
    )
    spec = AISessionSpec(
        session_id="idempotency-fence",
        objective="Preserve request identity.",
        instructions="Answer.",
        created_at=NOW,
    )
    await runtime.respond(
        spec,
        AITurnRequest(request_key="same-key", message="first payload", created_at=NOW),
    )
    with pytest.raises(ValueError, match="request_key reuse"):
        await runtime.respond(
            spec,
            AITurnRequest(request_key="same-key", message="different payload", created_at=NOW),
        )


def test_session_identity_cannot_be_rebound_after_restart(tmp_path) -> None:
    repo = SQLiteSessionRepository(tmp_path / "session.sqlite3")
    first = AISessionSpec(
        session_id="stable-session",
        objective="Objective A",
        instructions="Instructions A",
        created_at=NOW,
    )
    repo.ensure_session(first)

    reopened = SQLiteSessionRepository(tmp_path / "session.sqlite3")
    with pytest.raises(ValueError, match="different specification"):
        reopened.ensure_session(
            AISessionSpec(
                session_id="stable-session",
                objective="Objective B",
                instructions="Instructions A",
                created_at=NOW,
            )
        )
