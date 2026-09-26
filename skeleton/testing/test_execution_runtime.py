from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
from uuid import uuid4

import pytest

from skeleton.contracts.ai_execution import AIExecutionRequest, ExecutionState
from skeleton.intelligence.execution_runtime import (
    CognitiveExecutionError,
    CognitiveExecutionRuntime,
    ExecutionFinalizationBindings,
    ExecutionVerificationDecision,
)
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_contract import (
    FinishReason,
    ProviderToolCall,
    ProviderUsage,
)
from skeleton.provider_runtime import ProviderResponse
from skeleton.skills.tool_contract import (
    ToolApprovalPolicy,
    ToolAuthorityClass,
    ToolEffect,
    ToolIdempotencyMode,
    ToolManifest,
    ToolRiskClass,
    ToolSideEffectClass,
)
from skeleton.skills.tool_receipt_store import SQLiteToolReceiptStore
from skeleton.skills.tool_runtime import AsyncToolRuntime


def _now() -> datetime:
    return datetime(2026, 9, 23, 19, 30, tzinfo=timezone.utc)


def _request(
    *,
    execution_id: str = "exec-1",
    allowed_tools=(),
    stop_policy=None,
    budget=None,
    context_policy=None,
) -> AIExecutionRequest:
    return AIExecutionRequest(
        operation_id=str(uuid4()),
        execution_id=execution_id,
        objective="Complete the requested task.",
        context_policy={
            "tenant_id": "tenant-a",
            "data_class": "internal",
            **(context_policy or {}),
        },
        tool_policy={
            "tenant_id": "tenant-a",
            "allowed_tool_ids": list(allowed_tools),
        },
        resource_budget=budget
        or {
            "max_model_turns": 6,
            "max_tool_calls": 8,
        },
        stop_policy=stop_policy or {"max_repeat_tool_batches": 1},
        created_at=_now(),
    )


class FakeProvider:
    provider_id = "fake"
    model = "fake-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("provider called more times than expected")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _text_response(text: str, *, response_id: str) -> ProviderResponse:
    return ProviderResponse(
        text=text,
        provider="fake",
        model="fake-model",
        request_id=response_id,
        response_id=response_id,
        finish_reason=FinishReason.COMPLETED,
        usage=ProviderUsage(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            usage_source="provider",
        ),
    )


def _tool_response(
    call_id: str,
    *,
    tool_id: str = "repo.read",
    arguments=None,
    response_id: str = "resp-tool",
) -> ProviderResponse:
    return ProviderResponse(
        text=None,
        provider="fake",
        model="fake-model",
        request_id=response_id,
        response_id=response_id,
        tool_calls=(
            ProviderToolCall(
                call_id=call_id,
                tool_id=tool_id,
                arguments=arguments or {"path": "README.md"},
            ),
        ),
        finish_reason=FinishReason.TOOL_CALLS,
        usage=ProviderUsage(
            input_tokens=8,
            output_tokens=3,
            total_tokens=11,
            usage_source="provider",
        ),
    )


def _manifest(
    tool_id: str = "repo.read",
    *,
    approval_required: bool = False,
) -> ToolManifest:
    return ToolManifest(
        tool_id=tool_id,
        version="1.0.0",
        description="Read repository data",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        effect=(
            ToolEffect.REVERSIBLE
            if approval_required
            else ToolEffect.READ_ONLY
        ),
        approval_required=approval_required,
    )


def _verified_execution(
    _request: AIExecutionRequest,
    candidate: str,
    context_digest: str,
) -> ExecutionVerificationDecision:
    return ExecutionVerificationDecision(
        passed=True,
        receipt={
            "outcome": "passed",
            "policy_satisfied": True,
            "verifier_id": "test:deterministic",
            "candidate_digest": hashlib.sha256(
                candidate.encode("utf-8")
            ).hexdigest(),
            "context_digest": context_digest,
        },
        evidence_refs=("evidence:test-independent-source",),
    )


def _runtime(repo, provider, tools, **kwargs):
    kwargs.setdefault("verification_hook", _verified_execution)
    return CognitiveExecutionRuntime(repo, provider, tools, **kwargs)


@pytest.mark.asyncio
async def test_direct_provider_completion_is_verified_and_atomically_finalized() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    provider = FakeProvider([_text_response("done", response_id="resp-1")])
    runtime = _runtime(repo, provider, tools)
    request = _request()

    result = await runtime.start(
        request,
        instructions="Answer concisely.",
        prompt="Do the task.",
        context_digest="a" * 64,
        now=_now(),
    )

    assert result.completed is True
    assert result.state is ExecutionState.COMPLETED
    assert result.result is not None
    assert result.result.final_output == "done"
    assert result.result.verification is not None
    assert result.result.verification_receipt["outcome"] == "passed"
    assert result.result.stream_terminal_event.startswith("stream-terminal:exec-1:")
    assert len(repo.pending_outbox(execution_id="exec-1")) == 1
    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_provider_tool_projection_is_minimal_and_excludes_disabled_tools() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()

    async def handler(_request):
        return "artifact:read"

    rich_manifest = ToolManifest(
        tool_id="repo.read",
        version="2.0.0",
        description="Read repository data",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        capabilities=("repository.read", "citation.source"),
        authority_class=ToolAuthorityClass.READ,
        risk_class=ToolRiskClass.MEDIUM,
        side_effect_class=ToolSideEffectClass.NONE,
        idempotency_mode=ToolIdempotencyMode.INTRINSIC,
        approval_policy=ToolApprovalPolicy.NEVER,
        network_policy="none",
        data_policy="internal:repository",
        cost_model={"kind": "request", "estimated_units": 1},
        result_size_limit=65536,
        max_concurrency=8,
    )
    disabled_manifest = ToolManifest(
        tool_id="repo.disabled",
        version="1.0.0",
        description="Disabled internal tool",
        input_schema={
            "type": "object",
            "additionalProperties": False,
        },
        capabilities=("repository.internal",),
        authority_class=ToolAuthorityClass.PRIVILEGED,
        risk_class=ToolRiskClass.HIGH,
        side_effect_class=ToolSideEffectClass.NONE,
        idempotency_mode=ToolIdempotencyMode.INTRINSIC,
        approval_policy=ToolApprovalPolicy.POLICY,
        network_policy="none",
        data_policy="internal:restricted",
        cost_model={"kind": "disabled"},
        enabled=False,
    )
    await tools.register(rich_manifest, handler)
    await tools.register(disabled_manifest, handler)

    runtime = _runtime(repo, FakeProvider([]), tools)
    projected = await runtime._provider_tools(
        {"allowed_tool_ids": ["repo.read", "repo.disabled"]}
    )

    assert [item.tool_id for item in projected] == ["repo.read"]
    assert projected[0].as_dict() == {
        "tool_id": "repo.read",
        "description": "Read repository data",
        "input_schema": dict(rich_manifest.input_schema),
    }
    provider_payload = projected[0].as_dict()
    for internal_field in (
        "output_schema",
        "capabilities",
        "authority_class",
        "risk_class",
        "side_effect_class",
        "idempotency_mode",
        "approval_policy",
        "network_policy",
        "data_policy",
        "cost_model",
        "result_size_limit",
        "max_concurrency",
        "enabled",
    ):
        assert internal_field not in provider_payload


@pytest.mark.asyncio
async def test_model_tool_model_round_trip_uses_canonical_receipt_lineage() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    tool_requests = []

    async def handler(request):
        tool_requests.append(request)
        return "artifact:readme"

    await tools.register(_manifest(), handler)
    provider = FakeProvider(
        [
            _tool_response("call-1"),
            _text_response("final answer", response_id="resp-2"),
        ]
    )
    runtime = _runtime(repo, provider, tools)
    request = _request(allowed_tools=("repo.read",))

    result = await runtime.start(
        request,
        instructions="Use tools when needed.",
        prompt="Read the file and answer.",
        context_digest="b" * 64,
        now=_now(),
    )

    assert result.result.final_output == "final answer"
    assert [dict(item.arguments) for item in tool_requests] == [
        {"path": "README.md"}
    ]
    assert len(tool_requests) == 1
    provider_turn = repo.turns(request.execution_id)[0]
    assert tool_requests[0].execution_id == request.execution_id
    assert tool_requests[0].turn_id == provider_turn.turn_id
    assert tool_requests[0].call_id == "call-1"
    assert result.result.usage["model_turns"] == 2
    assert result.result.usage["tool_calls"] == 1
    assert len(result.result.tool_receipts) == 1
    assert len(repo.turns("exec-1")) == 3
    assert provider.requests[1].prompt.startswith("Tool results from the previous provider turn")


@pytest.mark.asyncio
async def test_approval_required_suspends_before_effect_and_resumes_once(
    tmp_path,
) -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime(
        receipt_store=SQLiteToolReceiptStore(
            tmp_path / "approval-tool-receipts.sqlite3"
        )
    )
    effects = []

    async def handler(request):
        effects.append(request.approval_ref)
        return "artifact:write"

    await tools.register(
        _manifest("repo.write", approval_required=True),
        handler,
    )
    provider = FakeProvider(
        [
            _tool_response("call-write", tool_id="repo.write"),
            _text_response("write confirmed", response_id="resp-final"),
        ]
    )
    runtime = _runtime(repo, provider, tools)
    request = _request(allowed_tools=("repo.write",))

    suspended = await runtime.start(
        request,
        instructions="Use the authorized tool.",
        prompt="Write the change.",
        context_digest="c" * 64,
        now=_now(),
    )

    assert suspended.completed is False
    assert suspended.state is ExecutionState.WAITING_FOR_USER
    assert [item.call_id for item in suspended.pending_approvals] == ["call-write"]
    assert effects == []

    approval_ref = suspended.pending_approvals[0].approval_ref
    assert approval_ref.startswith("approval:")

    completed = await runtime.resume(
        "exec-1",
        approval_refs={"call-write": approval_ref},
        now=_now(),
    )

    assert completed.completed is True
    assert completed.result.final_output == "write confirmed"
    assert effects == [approval_ref]
    assert len(provider.requests) == 2


@pytest.mark.asyncio
async def test_approval_resume_rejects_tampered_request_binding(tmp_path) -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime(
        receipt_store=SQLiteToolReceiptStore(
            tmp_path / "tampered-approval-tool-receipts.sqlite3"
        )
    )
    effects = []

    async def handler(request):
        effects.append(request.approval_ref)
        return "artifact:write"

    await tools.register(
        _manifest("repo.write", approval_required=True),
        handler,
    )
    provider = FakeProvider(
        [_tool_response("call-write", tool_id="repo.write")]
    )
    runtime = _runtime(repo, provider, tools)
    request = _request(
        execution_id="exec-tampered-approval",
        allowed_tools=("repo.write",),
    )

    suspended = await runtime.start(
        request,
        instructions="Use the authorized tool.",
        prompt="Write the change.",
        context_digest="c" * 64,
        now=_now(),
    )
    approval_ref = suspended.pending_approvals[0].approval_ref

    completed = await runtime.resume(
        request.execution_id,
        approval_refs={"call-write": approval_ref + "-tampered"},
        now=_now(),
    )

    assert completed.completed is True
    assert completed.result.status == "failed"
    assert completed.result.usage["error_code"] == "approval_binding_mismatch"
    assert effects == []
    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_crash_after_provider_checkpoint_resumes_without_second_provider_call(
    monkeypatch,
) -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    provider = FakeProvider([_text_response("checkpointed", response_id="resp-1")])
    runtime = _runtime(repo, provider, tools)
    request = _request()

    async def crash(*args, **kwargs):
        raise RuntimeError("simulated crash after provider checkpoint")

    monkeypatch.setattr(runtime, "_classify_provider_output", crash)

    with pytest.raises(RuntimeError, match="simulated crash"):
        await runtime.start(
            request,
            instructions="Answer.",
            prompt="Do it.",
            context_digest="d" * 64,
            now=_now(),
        )

    assert repo.get("exec-1").state is ExecutionState.CLASSIFYING_OUTPUT
    assert len(provider.requests) == 1

    resumed_provider = FakeProvider([])
    recovered = _runtime(repo, resumed_provider, tools)
    result = await recovered.resume("exec-1", now=_now())

    assert result.completed is True
    assert result.result.final_output == "checkpointed"
    assert resumed_provider.requests == []


@pytest.mark.asyncio
async def test_crash_after_tool_effect_resumes_without_duplicate_tool_effect() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    effects = []

    async def handler(request):
        effects.append(request.idempotency_key)
        return "artifact:read"

    await tools.register(_manifest(), handler)
    first_provider = FakeProvider(
        [
            _tool_response("call-1"),
            RuntimeError("simulated crash after tool checkpoint"),
        ]
    )
    runtime = _runtime(repo, first_provider, tools)
    request = _request(allowed_tools=("repo.read",))

    with pytest.raises(RuntimeError, match="simulated crash"):
        await runtime.start(
            request,
            instructions="Use tool.",
            prompt="Read and continue.",
            context_digest="e" * 64,
            now=_now(),
        )

    assert effects and len(effects) == 1
    assert repo.get("exec-1").state is ExecutionState.PROVIDER_PENDING

    restarted_tools = AsyncToolRuntime()

    async def duplicate_guard(request):
        effects.append("DUPLICATE")
        return "artifact:read"

    await restarted_tools.register(_manifest(), duplicate_guard)
    second_provider = FakeProvider(
        [_text_response("recovered final", response_id="resp-final")]
    )
    recovered = _runtime(
        repo,
        second_provider,
        restarted_tools,
    )

    result = await recovered.resume("exec-1", now=_now())

    assert result.result.final_output == "recovered final"
    assert effects == [effects[0]]
    assert len(second_provider.requests) == 1


@pytest.mark.asyncio
async def test_repeated_identical_tool_batches_trip_cycle_limit() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    calls = []

    async def handler(request):
        calls.append(request.idempotency_key)
        return "artifact:read"

    await tools.register(_manifest(), handler)
    provider = FakeProvider(
        [
            _tool_response("call-1"),
            _tool_response("call-2", response_id="resp-tool-2"),
            _tool_response("call-3", response_id="resp-tool-3"),
        ]
    )
    runtime = _runtime(repo, provider, tools)
    request = _request(
        allowed_tools=("repo.read",),
        stop_policy={"max_repeat_tool_batches": 1},
    )

    result = await runtime.start(
        request,
        instructions="Use tool if necessary.",
        prompt="Keep reading.",
        context_digest="f" * 64,
        now=_now(),
    )

    assert result.result.status == "failed"
    assert result.result.usage["error_code"] == "tool_cycle_detected"
    assert len(calls) == 2
    assert len(provider.requests) == 3


@pytest.mark.asyncio
async def test_cancellation_while_waiting_for_approval_finalizes_without_effect(
    tmp_path,
) -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime(
        receipt_store=SQLiteToolReceiptStore(
            tmp_path / "cancel-tool-receipts.sqlite3"
        )
    )
    effects = []

    async def handler(request):
        effects.append("effect")
        return "artifact:write"

    await tools.register(
        _manifest("repo.write", approval_required=True),
        handler,
    )
    provider = FakeProvider(
        [_tool_response("call-write", tool_id="repo.write")]
    )
    runtime = _runtime(repo, provider, tools)
    request = _request(allowed_tools=("repo.write",))

    suspended = await runtime.start(
        request,
        instructions="Use authorized tools only.",
        prompt="Write.",
        context_digest="1" * 64,
        now=_now(),
    )
    current = repo.get("exec-1")
    repo.request_cancel(
        "exec-1",
        expected_version=current.version,
        now=_now(),
    )

    cancelled = await runtime.resume("exec-1", now=_now())

    assert suspended.state is ExecutionState.WAITING_FOR_USER
    assert cancelled.result.status == "cancelled"
    assert cancelled.state is ExecutionState.CANCELLED
    assert effects == []


@pytest.mark.asyncio
async def test_cancellation_during_provider_io_fences_late_result() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    started = asyncio.Event()
    release = asyncio.Event()

    class GateProvider:
        provider_id = "fake"
        model = "fake-model"

        def __init__(self) -> None:
            self.requests = []

        async def generate(self, request):
            self.requests.append(request)
            started.set()
            await release.wait()
            return _text_response(
                "must-not-become-final-output",
                response_id="resp-late-cancel",
            )

    provider = GateProvider()
    runtime = _runtime(repo, provider, tools)
    task = asyncio.create_task(
        runtime.start(
            _request(),
            instructions="Answer.",
            prompt="Wait for cancellation.",
            context_digest="c" * 64,
            now=_now(),
        )
    )

    await started.wait()
    current = repo.get("exec-1")
    repo.request_cancel(
        "exec-1",
        expected_version=current.version,
        now=_now(),
    )
    release.set()
    result = await task

    assert result.state is ExecutionState.CANCELLED
    assert result.result is not None
    assert result.result.status == "cancelled"
    assert result.result.final_output is None
    assert result.result.usage["error_code"] == "cancellation_requested"
    assert result.result.provider_receipts == (
        "provider:fake:resp-late-cancel",
    )
    assert result.result.usage["provider_usage"][0]["total_tokens"] == 15
    checkpoint = repo.latest_checkpoint("exec-1")
    assert checkpoint is not None
    assert checkpoint.payload["last_provider"]["late_result_fenced"] is True


@pytest.mark.asyncio
async def test_expired_deadline_fails_before_provider_io() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    provider = FakeProvider([])
    request = _request(
        stop_policy={
            "max_repeat_tool_batches": 1,
            "deadline": (_now() - timedelta(seconds=1)).isoformat(),
        }
    )
    runtime = _runtime(repo, provider, tools)

    result = await runtime.start(
        request,
        instructions="Answer.",
        prompt="Do it.",
        context_digest="2" * 64,
        now=_now(),
    )

    assert result.result.status == "failed"
    assert result.result.usage["error_code"] == "execution_deadline_exceeded"
    assert provider.requests == []



@pytest.mark.asyncio
async def test_tool_handler_outage_becomes_durable_execution_failure() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()

    async def unavailable_handler(_request):
        raise RuntimeError("tool unavailable")

    await tools.register(_manifest(), unavailable_handler)
    provider = FakeProvider([_tool_response("call-outage")])
    runtime = _runtime(repo, provider, tools)
    request = _request(allowed_tools=("repo.read",))

    result = await runtime.start(
        request,
        instructions="Use the tool if required.",
        prompt="Read the file.",
        context_digest="3" * 64,
        now=_now(),
    )

    assert result.completed is True
    assert result.result is not None
    assert result.result.status == "failed"
    assert result.result.usage["error_code"] == "RuntimeError"
    assert len(result.result.tool_receipts) == 1
    assert len(provider.requests) == 1
    assert repo.result("exec-1") == result.result


@pytest.mark.asyncio
async def test_default_verification_fails_closed_without_external_evidence() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    provider = FakeProvider([_text_response("unverified", response_id="resp-unverified")])
    runtime = CognitiveExecutionRuntime(repo, provider, tools)

    result = await runtime.start(
        _request(),
        instructions="Answer.",
        prompt="Return a model-generated structured answer.",
        context_digest="9" * 64,
        now=_now(),
    )

    assert result.completed is True
    assert result.state is ExecutionState.FAILED
    assert result.result is not None
    assert result.result.status == "failed"
    assert result.result.usage["error_code"] == "verification_failed"
    assert result.result.verification_receipt["outcome"] == "unknown"
    assert result.result.verification_receipt["policy_satisfied"] is False
    assert "authoritative_support_missing" in result.result.verification_receipt["issues"]


@pytest.mark.asyncio
async def test_assistant_proposal_verification_completes_without_external_evidence() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    provider = FakeProvider([_text_response("proposal", response_id="resp-proposal")])
    runtime = CognitiveExecutionRuntime(repo, provider, tools)

    result = await runtime.start(
        _request(
            context_policy={
                "capability": "assistant.compat",
                "verification_profile": "assistant_proposal",
            }
        ),
        instructions="Offer a bounded proposal.",
        prompt="Suggest a refactor.",
        context_digest="a" * 64,
        now=_now(),
    )

    assert result.completed is True
    assert result.state is ExecutionState.COMPLETED
    assert result.result is not None
    assert result.result.status == "completed"
    assert result.result.final_output == "proposal"
    assert result.result.evidence_refs == ()
    receipt = result.result.verification_receipt
    assert receipt["verification_profile"] == "assistant_proposal"
    assert receipt["claim_kind"] == "hypothesis"
    assert receipt["risk"] == "low"
    assert receipt["outcome"] == "passed"
    assert receipt["policy_satisfied"] is True
    assert receipt["policy"]["level"] == 0
    assert receipt["policy"]["required_modes"] == ["structural"]


@pytest.mark.asyncio
async def test_assistant_proposal_profile_rejects_tool_enabled_execution() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    await tools.register(_manifest(), lambda _request: {"ok": True})
    provider = FakeProvider([_text_response("unsafe proposal", response_id="resp-tool-profile")])
    runtime = CognitiveExecutionRuntime(repo, provider, tools)

    with pytest.raises(
        CognitiveExecutionError,
        match="tool-free execution",
    ):
        await runtime.start(
            _request(
                allowed_tools=("repo.read",),
                context_policy={
                    "capability": "assistant.compat",
                    "verification_profile": "assistant_proposal",
                },
            ),
            instructions="Answer.",
            prompt="Do not call tools.",
            context_digest="b" * 64,
            now=_now(),
        )


@pytest.mark.asyncio
async def test_assistant_proposal_profile_rejects_non_assistant_capability() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    provider = FakeProvider([_text_response("proposal", response_id="resp-wrong-cap")])
    runtime = CognitiveExecutionRuntime(repo, provider, tools)

    with pytest.raises(
        CognitiveExecutionError,
        match="assistant capability",
    ):
        await runtime.start(
            _request(
                context_policy={
                    "capability": "admin.execute",
                    "verification_profile": "assistant_proposal",
                }
            ),
            instructions="Answer.",
            prompt="Do something.",
            context_digest="c" * 64,
            now=_now(),
        )


def test_verification_adapter_rejects_bare_pass_without_external_evidence() -> None:
    with pytest.raises(
        CognitiveExecutionError,
        match="external evidence refs",
    ):
        ExecutionVerificationDecision(
            passed=True,
            receipt={
                "outcome": "passed",
                "policy_satisfied": True,
                "verifier_id": "test:unsafe-bare-pass",
            },
        )


def test_verification_adapter_rejects_inconsistent_pass_receipt() -> None:
    with pytest.raises(
        CognitiveExecutionError,
        match="policy_satisfied",
    ):
        ExecutionVerificationDecision(
            passed=True,
            receipt={
                "outcome": "passed",
                "policy_satisfied": False,
                "verifier_id": "test:inconsistent",
            },
            evidence_refs=("evidence:test-source",),
        )


@pytest.mark.asyncio
async def test_finalization_binding_refs_are_committed_with_terminal_result() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    provider = FakeProvider([_text_response("bound", response_id="resp-bound")])

    async def bindings(_request, candidate, _payload):
        assert candidate == "bound"
        return ExecutionFinalizationBindings(
            memory_refs=("memory:turn-summary",),
            artifact_refs=("artifact:answer",),
        )

    runtime = _runtime(
        repo,
        provider,
        tools,
        finalization_binding_hook=bindings,
    )
    result = await runtime.start(
        _request(),
        instructions="Answer.",
        prompt="Bind final lineage.",
        context_digest="7" * 64,
        now=_now(),
    )

    assert result.result is not None
    assert result.result.memory_refs == ("memory:turn-summary",)
    assert result.result.artifact_refs == ("artifact:answer",)
    pending = repo.pending_outbox(execution_id="exec-1")
    assert pending[0].payload["memory_refs"] == ["memory:turn-summary"]
    assert pending[0].payload["artifact_refs"] == ["artifact:answer"]


@pytest.mark.asyncio
async def test_resume_commits_staged_terminal_intent_without_replaying_verification(
    monkeypatch,
) -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    provider = FakeProvider([_text_response("recover me", response_id="resp-recover")])
    verification_calls = []
    binding_calls = []

    def verify(_request, candidate, _context_digest):
        verification_calls.append(candidate)
        return ExecutionVerificationDecision(
            passed=True,
            receipt={
                "outcome": "passed",
                "policy_satisfied": True,
                "verifier_id": "test:recovery",
            },
            evidence_refs=("evidence:independent",),
        )

    def bindings(_request, candidate, _payload):
        binding_calls.append(candidate)
        return ExecutionFinalizationBindings(
            memory_refs=("memory:recover",),
            artifact_refs=("artifact:recover",),
        )

    runtime = CognitiveExecutionRuntime(
        repo,
        provider,
        tools,
        verification_hook=verify,
        finalization_binding_hook=bindings,
    )
    real_finalize_staged = repo.finalize_staged

    def crash_before_terminal_commit(*args, **kwargs):
        raise RuntimeError("simulated crash after finalization intent")

    monkeypatch.setattr(repo, "finalize_staged", crash_before_terminal_commit)
    with pytest.raises(RuntimeError, match="simulated crash"):
        await runtime.start(
            _request(),
            instructions="Answer.",
            prompt="Recover finalization.",
            context_digest="8" * 64,
            now=_now(),
        )

    staged = repo.finalization_intent("exec-1")
    assert staged is not None
    assert staged.result.memory_refs == ("memory:recover",)
    assert staged.result.artifact_refs == ("artifact:recover",)
    assert verification_calls == ["recover me"]
    assert binding_calls == ["recover me"]

    monkeypatch.setattr(repo, "finalize_staged", real_finalize_staged)

    def forbidden_verification(*_args, **_kwargs):
        raise AssertionError("verification must not replay after staged intent")

    recovered = CognitiveExecutionRuntime(
        repo,
        FakeProvider([]),
        tools,
        verification_hook=forbidden_verification,
    )
    result = await recovered.resume("exec-1", now=_now())

    assert result.completed is True
    assert result.result is not None
    assert result.result.final_output == "recover me"
    assert result.result.memory_refs == ("memory:recover",)
    assert result.result.artifact_refs == ("artifact:recover",)
    assert repo.finalization_intent("exec-1") is None
    assert len(repo.pending_outbox(execution_id="exec-1")) == 1

@pytest.mark.asyncio
async def test_cognitive_runtime_meters_checkpoint_turn_and_terminal_storage() -> None:
    repo = SQLiteExecutionRepository()
    tools = AsyncToolRuntime()
    provider = FakeProvider(
        [_text_response("metered answer", response_id="resp-meter-storage")]
    )
    events = []

    def meter(resource_id, write_id, payload, meter_now):
        events.append((resource_id, write_id, payload, meter_now))

    runtime = CognitiveExecutionRuntime(
        repo,
        provider,
        tools,
        storage_meter=meter,
    )
    result = await runtime.start(
        _request(
            context_policy={
                "capability": "assistant.chat",
                "verification_profile": "assistant_proposal",
            }
        ),
        instructions="Answer.",
        prompt="Return a bounded answer.",
        context_digest="d" * 64,
        now=_now(),
    )

    assert result.completed is True
    assert result.result is not None
    resources = [item[0] for item in events]
    assert "execution-checkpoint" in resources
    assert "execution-turn" in resources
    assert "execution-finalization-intent" in resources
    assert "execution-result" in resources

    write_ids = [item[1] for item in events]
    assert len(write_ids) == len(set(write_ids))
    assert any(item.startswith("checkpoint:exec-1:") for item in write_ids)
    assert any(item.startswith("turn:exec-1:") for item in write_ids)
    assert "intent:exec-1" in write_ids
    assert "result:exec-1" in write_ids

    for _resource_id, _write_id, payload, meter_now in events:
        assert payload is not None
        assert meter_now == _now()
