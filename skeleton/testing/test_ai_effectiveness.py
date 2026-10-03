from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import threading

import pytest

from skeleton.ai.runtime.functional_ai import FunctionalAIRequest, FunctionalAIRuntime
from skeleton.ai.runtime.inference import (
    CallableLocalModel,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalModelAdapter,
    LocalToolCall,
)
from skeleton.intelligence.execution_runtime import ExecutionVerificationDecision
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.skills.tool_contract import (
    ToolAuthorityClass,
    ToolEffect,
    ToolIdempotencyMode,
    ToolManifest,
    ToolRiskClass,
    ToolSideEffectClass,
)
from skeleton.skills.tool_receipt_store import SQLiteToolReceiptStore
from skeleton.skills.tool_runtime import AsyncToolRuntime


NOW = datetime(2026, 10, 2, 19, 45, tzinfo=timezone.utc)


def _effect_model() -> LocalModelAdapter:
    model_digest = hashlib.sha256(b"effectiveness-local-model-v1").hexdigest()

    def runner(
        request: LocalInferenceRequest,
        cancel: threading.Event,
    ) -> LocalInferenceResult:
        assert not cancel.is_set()
        if request.prompt.startswith("Tool results from the previous provider turn"):
            return LocalInferenceResult(
                text="The requested state change completed.",
                model_id="effectiveness-local-model",
                model_digest=model_digest,
                input_tokens=len(request.rendered_input.split()),
                output_tokens=6,
                response_id="local:effectiveness-final",
            )

        assert any(tool.get("tool_id") == "state.set" for tool in request.tools)
        return LocalInferenceResult(
            text=None,
            model_id="effectiveness-local-model",
            model_digest=model_digest,
            input_tokens=len(request.rendered_input.split()),
            output_tokens=4,
            finish_reason="tool_calls",
            response_id="local:effectiveness-tool",
            tool_calls=(
                LocalToolCall(
                    call_id="effect-set-1",
                    tool_id="state.set",
                    arguments={"key": "mode", "value": "effective"},
                ),
            ),
        )

    return LocalModelAdapter(
        LocalInferenceEngine(
            CallableLocalModel(
                model_id="effectiveness-local-model",
                model_digest=model_digest,
                runner=runner,
            )
        )
    )


def _request(request_id: str) -> FunctionalAIRequest:
    return FunctionalAIRequest(
        request_id=request_id,
        objective="Cause one governed reversible state change and report the outcome.",
        prompt="Set mode to effective, then report whether the change completed.",
        instructions="Use only the supplied local model and governed tool.",
        context_digest=hashlib.sha256(b"effectiveness-context").hexdigest(),
        allowed_tool_ids=("state.set",),
        created_at=NOW,
    )


def _external_verification(
    _request,
    candidate: str,
    context_digest: str,
) -> ExecutionVerificationDecision:
    assert candidate == "The requested state change completed."
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "test:independent-effect-verifier",
            "candidate_digest": hashlib.sha256(candidate.encode()).hexdigest(),
            "context_digest": context_digest,
        },
        evidence_refs=("evidence:independent-effect-verifier",),
    )


def _effect_manifest() -> ToolManifest:
    return ToolManifest(
        tool_id="state.set",
        version="1.0.0",
        description="Set one bounded local state key.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
            "additionalProperties": False,
        },
        authority_class=ToolAuthorityClass.WRITE,
        risk_class=ToolRiskClass.MEDIUM,
        side_effect_class=ToolSideEffectClass.LOCAL_REVERSIBLE,
        idempotency_mode=ToolIdempotencyMode.IDEMPOTENCY_KEY,
        network_policy="none",
        data_policy="internal",
        effect=ToolEffect.REVERSIBLE,
    )


@pytest.mark.asyncio
async def test_effectful_functional_ai_requires_and_records_postcondition(
    tmp_path,
) -> None:
    state: dict[str, str] = {}
    observed_requests = []
    tools = AsyncToolRuntime(
        receipt_store=SQLiteToolReceiptStore(tmp_path / "tool-effects.sqlite3")
    )

    async def set_handler(request):
        observed_requests.append(request)
        state[str(request.arguments["key"])] = str(request.arguments["value"])
        return "state:mode"

    async def postcondition(request, _result_ref):
        return state.get(str(request.arguments["key"])) == str(
            request.arguments["value"]
        )

    await tools.register(
        _effect_manifest(),
        set_handler,
        postcondition=postcondition,
    )
    repository = SQLiteExecutionRepository(tmp_path / "execution.sqlite3")
    runtime = FunctionalAIRuntime(
        repository,
        _effect_model(),
        tools,
        verification_hook=_external_verification,
    )

    request = _request("effectiveness-postcondition-pass")
    run = await runtime.execute(request)

    assert state == {"mode": "effective"}
    assert run.execution.completed is True
    assert run.execution.result is not None
    assert run.execution.result.status == "completed"
    assert (
        run.execution.result.verification_receipt["verifier_id"]
        == "test:independent-effect-verifier"
    )
    assert len(observed_requests) == 1

    tool_request = observed_requests[0]
    receipt = await tools.receipt(
        tenant_id=tool_request.tenant_id,
        operation_id=tool_request.operation_id,
        idempotency_key=tool_request.idempotency_key,
    )
    assert receipt is not None
    assert receipt.postcondition_verified is True
    assert receipt.result_ref == "state:mode"


@pytest.mark.asyncio
async def test_external_verifier_cannot_publish_unproven_effect(
    tmp_path,
) -> None:
    state: dict[str, str] = {}
    observed_requests = []
    tools = AsyncToolRuntime(
        receipt_store=SQLiteToolReceiptStore(tmp_path / "tool-effects.sqlite3")
    )

    async def set_handler(request):
        observed_requests.append(request)
        state[str(request.arguments["key"])] = str(request.arguments["value"])
        return "state:mode"

    # Deliberately register no postcondition. The external verifier is
    # permissive, so only the runtime effect guard can prevent false success.
    await tools.register(_effect_manifest(), set_handler)
    repository = SQLiteExecutionRepository(tmp_path / "execution.sqlite3")
    runtime = FunctionalAIRuntime(
        repository,
        _effect_model(),
        tools,
        verification_hook=_external_verification,
    )

    request = _request("effectiveness-postcondition-block")
    with pytest.raises(RuntimeError, match="VS-001 did not complete"):
        await runtime.execute(request)

    # The mutation did happen, but the system must not claim verified success
    # without an observed postcondition for that effect.
    assert state == {"mode": "effective"}
    assert len(observed_requests) == 1

    stored = repository.result(request.execution_id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.usage["error_code"] == "verification_blocked"
    assert stored.verification_receipt is not None
    assert (
        stored.verification_receipt["verifier_id"]
        == "execution-runtime:effect-postcondition-guard"
    )
    assert stored.verification_receipt["claim_kind"] == "action_outcome"
    assert stored.verification_receipt["action_effect"] == "reversible"
    assert stored.verification_receipt["required_modes"] == ["postcondition"]
    assert len(
        stored.verification_receipt["missing_postcondition_receipt_ids"]
    ) == 1
