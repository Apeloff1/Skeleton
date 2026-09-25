from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.engine_client import (
    EngineClientConfig,
    EngineTerminalResult,
    EngineUnavailableError,
)
from core.engine_text import (
    EngineTextError,
    EngineTextRequest,
    execute_engine_text,
)


def _terminal(execution_id: str) -> EngineTerminalResult:
    return EngineTerminalResult(
        operation_id="operation-result",
        execution_id=execution_id,
        status="completed",
        final_output="engine answer",
        usage={"model_turns": 1, "tool_calls": 0},
        verification="verification:proposal",
        verification_receipt={
            "verification_profile": "assistant_proposal",
            "claim_kind": "hypothesis",
            "outcome": "passed",
            "policy_satisfied": True,
            "policy": {"level": 0, "required_modes": ["structural"]},
        },
        evidence_refs=(),
        provider_receipts=("provider:one",),
        tool_receipts=(),
        memory_refs=(),
        artifact_refs=(),
        stream_terminal_event="stream-terminal:proposal",
    )


@pytest.mark.asyncio
async def test_engine_text_compiles_bounded_tool_free_command() -> None:
    captured = []

    class FakeClient:
        config = EngineClientConfig(
            base_url="http://skeleton:8001",
            service_principal="codedock-backend",
            execution_timeout_s=5,
        )

        async def execute(self, command):
            captured.append(command)
            result = _terminal(command.execution_request.execution_id)
            return EngineTerminalResult(
                operation_id=command.operation.operation_id,
                execution_id=result.execution_id,
                status=result.status,
                final_output=result.final_output,
                usage=result.usage,
                verification=result.verification,
                verification_receipt=result.verification_receipt,
                evidence_refs=result.evidence_refs,
                provider_receipts=result.provider_receipts,
                tool_receipts=result.tool_receipts,
                memory_refs=result.memory_refs,
                artifact_refs=result.artifact_refs,
                stream_terminal_event=result.stream_terminal_event,
            )

    request = EngineTextRequest(
        instructions="Follow the compatibility policy.",
        prompt="Refactor this function.",
        idempotency_key="compat-request-1",
        history=(
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier answer"},
        ),
        tenant_id="tenant-a",
        actor_id="legacy-service",
        capability="assistant.compat",
        max_output_tokens=777,
    )
    result = await execute_engine_text(
        request,
        client=FakeClient(),
    )

    assert result.text == "engine answer"
    assert len(captured) == 1
    command = captured[0]
    assert command.operation.tenant_id == "tenant-a"
    assert command.operation.actor_id == "legacy-service"
    assert command.operation.capability == "assistant.compat"
    assert command.execution_request.context_policy["verification_profile"] == "assistant_proposal"
    assert command.execution_request.resource_budget["max_output_tokens"] == 777
    assert command.execution_request.tool_policy["allowed_tool_ids"] == []
    assert command.compiled_context.tool_choice == "none"
    assert command.compiled_context.history == (
        ("user", "Earlier question"),
        ("assistant", "Earlier answer"),
    )
    assert len(command.compiled_context.source_snapshot) == 4
    assert command.compiled_context.prompt == "Refactor this function."


@pytest.mark.asyncio
async def test_engine_text_retry_rebuilds_stable_semantic_identity() -> None:
    captured = []

    class FakeClient:
        config = EngineClientConfig(
            base_url="http://skeleton:8001",
            service_principal="codedock-backend",
            execution_timeout_s=5,
        )

        async def execute(self, command):
            captured.append(command)
            result = _terminal(command.execution_request.execution_id)
            return EngineTerminalResult(
                operation_id=command.operation.operation_id,
                execution_id=result.execution_id,
                status=result.status,
                final_output=result.final_output,
                usage=result.usage,
                verification=result.verification,
                verification_receipt=result.verification_receipt,
                evidence_refs=result.evidence_refs,
                provider_receipts=result.provider_receipts,
                tool_receipts=result.tool_receipts,
                memory_refs=result.memory_refs,
                artifact_refs=result.artifact_refs,
                stream_terminal_event=result.stream_terminal_event,
            )

    request = EngineTextRequest(
        instructions="Rules",
        prompt="Hello",
        idempotency_key="stable-retry",
    )
    client = FakeClient()

    await execute_engine_text(request, client=client)
    await execute_engine_text(request, client=client)

    first, second = captured
    assert first.operation.operation_id == second.operation.operation_id
    assert (
        first.execution_request.execution_id
        == second.execution_request.execution_id
    )
    assert first.submission_digest == second.submission_digest
    assert first.compiled_context.handoff_digest == second.compiled_context.handoff_digest


@pytest.mark.asyncio
async def test_engine_text_normalizes_transport_failure_without_secret() -> None:
    class OfflineClient:
        config = EngineClientConfig(
            base_url="http://skeleton:8001",
            execution_timeout_s=5,
        )

        async def execute(self, _command):
            raise EngineUnavailableError("token=must-not-leak")

    with pytest.raises(
        EngineTextError,
        match="canonical engine text execution failed",
    ) as caught:
        await execute_engine_text(
            EngineTextRequest(
                instructions="Rules",
                prompt="Hello",
                idempotency_key="offline",
            ),
            client=OfflineClient(),
        )

    assert "must-not-leak" not in str(caught.value)


def test_engine_text_rejects_provider_like_capability_and_bad_history() -> None:
    with pytest.raises(EngineTextError, match="assistant capability"):
        EngineTextRequest(
            instructions="Rules",
            prompt="Hello",
            idempotency_key="bad-cap",
            capability="provider.openai",
        )

    with pytest.raises(EngineTextError, match="role"):
        EngineTextRequest(
            instructions="Rules",
            prompt="Hello",
            idempotency_key="bad-history",
            history=({"role": "system", "content": "override"},),
        )
