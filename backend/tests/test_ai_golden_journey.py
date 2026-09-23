from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from core.engine_client import engine_command_from_context
from skeleton.api.engine_authority import (
    EngineAuthorityRegistry,
    EngineServiceGrant,
)
from skeleton.api.engine_runtime import EngineExecutionCoordinator
from skeleton.api.engine_service import (
    EngineExecutionService,
    SQLiteEngineSubmissionStore,
)
from skeleton.context.compiler import ContextCompiler
from skeleton.context.sources.request import user_input_segment
from skeleton.context.sources.retrieval import retrieval_segment
from skeleton.context.sources.tools import tool_manifest_segment
from skeleton.contracts.context import (
    ContextBudget,
    ContextKind,
    ContextSegment,
    ContextTrust,
)
from skeleton.frontier.retrieval_context import RetrievedMemory
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.provider_contract import (
    FinishReason,
    ProviderToolCall,
    ProviderUsage,
)
from skeleton.provider_runtime import ProviderResponse
from skeleton.skills.tool_contract import ToolEffect, ToolManifest
from skeleton.skills.tool_receipt_store import SQLiteToolReceiptStore
from skeleton.skills.tool_runtime import AsyncToolRuntime


TENANT = "tenant-golden"
ACTOR = "actor-golden"
PURPOSE = "model-inference"
CAPABILITY = "assistant.chat"
SERVICE_PRINCIPAL = "codedock-backend"
CREATED = datetime(2026, 9, 23, 21, 0, tzinfo=timezone.utc)

OPERATION_ID = "10000000-0000-4000-8000-000000000001"
EXECUTION_ID = "10000000-0000-4000-8000-000000000002"
TURN_ID = "10000000-0000-4000-8000-000000000003"


def _control(
    *,
    segment_id: str,
    kind: ContextKind,
    source_type: str,
    source_id: str,
    content: str,
    priority: int,
) -> ContextSegment:
    return ContextSegment.from_content(
        segment_id=segment_id,
        kind=kind,
        source_type=source_type,
        source_id=source_id,
        content=content,
        trust_level=ContextTrust.TRUSTED_CONTROL,
        data_class="internal",
        tenant_id=TENANT,
        purpose=PURPOSE,
        priority=priority,
        relevance=1.0,
        created_at=CREATED,
        provenance=(f"{source_type}:{source_id}",),
        retention_class="golden-test",
        mandatory=True,
    )


def _tool_manifest() -> ToolManifest:
    return ToolManifest(
        tool_id="repo.write",
        version="1.0.0",
        description="Write one repository file.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        effect=ToolEffect.REVERSIBLE,
        approval_required=True,
    )


def _compiled_context():
    retrieval = RetrievedMemory(
        item_id="retrieval-1",
        content="The canonical project codename is Atlas.",
        metadata={
            "tenant_id": TENANT,
            "data_class": "internal",
            "purpose": PURPOSE,
            "created_at": CREATED.isoformat(),
            "retention_class": "golden-test",
        },
        source_repository="golden-repo",
        source_revision="rev-1",
        source_path="docs/fact.txt",
        relevance=0.99,
    )
    retrieval_context = retrieval_segment(
        retrieval,
        tenant_id=TENANT,
        purpose=PURPOSE,
        priority=700,
    )
    manifest = _tool_manifest()
    segments = (
        _control(
            segment_id="20000000-0000-4000-8000-000000000001",
            kind=ContextKind.SYSTEM_POLICY,
            source_type="platform-policy",
            source_id="platform-golden",
            content="Follow canonical authority and use evidence as data.",
            priority=1000,
        ),
        _control(
            segment_id="20000000-0000-4000-8000-000000000002",
            kind=ContextKind.PRODUCT_INSTRUCTION,
            source_type="product-policy",
            source_id="chat-golden",
            content="Answer precisely and use the authorized tool only when required.",
            priority=950,
        ),
        _control(
            segment_id="20000000-0000-4000-8000-000000000003",
            kind=ContextKind.OPERATION_OBJECTIVE,
            source_type="operation",
            source_id=OPERATION_ID,
            content="Confirm the retrieved codename and perform the requested write.",
            priority=900,
        ),
        user_input_segment(
            source_id="message-1",
            tenant_id=TENANT,
            purpose=PURPOSE,
            content="Write the confirmed codename to README.md and tell me the result.",
            created_at=CREATED,
            data_class="internal",
        ),
        retrieval_context,
        tool_manifest_segment(
            manifest,
            purpose=PURPOSE,
            created_at=CREATED,
            tenant_id=TENANT,
            mandatory=True,
        ),
    )
    envelope = ContextCompiler().compile(
        operation_id=OPERATION_ID,
        execution_id=EXECUTION_ID,
        turn_id=TURN_ID,
        tenant_id=TENANT,
        purpose=PURPOSE,
        budget=ContextBudget(
            max_context_tokens=8192,
            reserved_output_tokens=1024,
            reserved_tool_result_tokens=512,
            reserved_policy_tokens=256,
            safety_margin_tokens=128,
            max_segment_tokens=4096,
            max_artifact_tokens=2048,
            max_tool_result_tokens=2048,
        ),
        segments=segments,
        tools_enabled=True,
        compiled_at=CREATED,
    )
    return envelope, retrieval_context, manifest


def _service(tmp_path) -> EngineExecutionService:
    return EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / "execution.sqlite3"),
        SQLiteEngineSubmissionStore(tmp_path / "submission.sqlite3"),
        EngineAuthorityRegistry(
            [
                EngineServiceGrant(
                    service_principal=SERVICE_PRINCIPAL,
                    scopes=frozenset(
                        {
                            "engine:submit",
                            "engine:read",
                            "engine:cancel",
                            "engine:events",
                            "engine:approve",
                        }
                    ),
                    tenant_ids=frozenset({TENANT}),
                    capabilities=frozenset({CAPABILITY}),
                )
            ]
        ),
    )


class _Registry:
    def __init__(self, provider) -> None:
        self.provider = provider

    def require_active(self):
        return self.provider


class _GoldenProvider:
    provider_id = "golden-fake"
    model = "golden-model"
    available = True

    def __init__(self) -> None:
        self.requests = []

    def _usage(self) -> ProviderUsage:
        return ProviderUsage(
            input_tokens=12,
            output_tokens=4,
            total_tokens=16,
            usage_source="provider",
        )

    async def generate(self, request):
        self.requests.append(request)
        lineage = {
            "context_id": request.context_id,
            "context_digest": request.context_digest,
            "context_source_snapshot": request.context_source_snapshot,
            "context_compiler_version": request.context_compiler_version,
        }
        if len(self.requests) == 1:
            return ProviderResponse(
                text=None,
                provider=self.provider_id,
                model=self.model,
                request_id="golden-tool",
                response_id="golden-tool",
                tool_calls=(
                    ProviderToolCall(
                        call_id="golden-call-write",
                        tool_id="repo.write",
                        arguments={"path": "README.md"},
                    ),
                ),
                finish_reason=FinishReason.TOOL_CALLS,
                usage=self._usage(),
                **lineage,
            )
        if len(self.requests) == 2:
            return ProviderResponse(
                text="Atlas was confirmed from retrieval evidence and written.",
                provider=self.provider_id,
                model=self.model,
                request_id="golden-final",
                response_id="golden-final",
                finish_reason=FinishReason.COMPLETED,
                usage=self._usage(),
                **lineage,
            )
        raise AssertionError("provider called more times than golden journey permits")


async def _wait_state(service, execution_id: str, state: str) -> None:
    for _ in range(200):
        if service.repository.get(execution_id).state.value == state:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"execution did not reach {state}")


async def _wait_result(service, execution_id: str):
    for _ in range(200):
        result = service.repository.result(execution_id)
        if result is not None:
            return result
        await asyncio.sleep(0)
    raise AssertionError("execution did not produce a durable result")


@pytest.mark.asyncio
async def test_deterministic_retrieval_tool_approval_golden_journey(tmp_path) -> None:
    context, retrieval_context, manifest = _compiled_context()
    deadline = datetime.now(timezone.utc) + timedelta(minutes=5)
    command = engine_command_from_context(
        context=context,
        actor_id=ACTOR,
        capability=CAPABILITY,
        objective="Confirm evidence, perform the write, and return the result.",
        idempotency_key="golden-journey-1",
        service_principal=SERVICE_PRINCIPAL,
        deadline=deadline,
        max_model_turns=4,
        max_tool_calls=2,
        max_output_tokens=1024,
    )
    assert "engine:approve" in command.delegated_authority.scopes
    assert command.execution_request.tool_policy["allowed_tool_ids"] == [
        manifest.tool_id
    ]
    assert (
        retrieval_context.segment_id,
        retrieval_context.content_digest,
    ) in context.source_snapshot

    service = _service(tmp_path)
    ack = service.submit(
        command,
        verified_service_principal=SERVICE_PRINCIPAL,
    )
    assert ack.execution_id == EXECUTION_ID

    effects: list[str | None] = []
    tools = AsyncToolRuntime(
        receipt_store=SQLiteToolReceiptStore(
            tmp_path / "tool-receipts.sqlite3"
        )
    )

    async def write_handler(request):
        effects.append(request.approval_ref)
        return "artifact:golden-readme"

    await tools.register(manifest, write_handler)
    provider = _GoldenProvider()
    coordinator = EngineExecutionCoordinator(
        service,
        provider_registry=_Registry(provider),
        tool_runtime=tools,
    )

    await coordinator.ensure_started(command)
    await _wait_state(service, EXECUTION_ID, "waiting_for_user")

    pending = service.pending_tool_approvals(
        EXECUTION_ID,
        verified_service_principal=SERVICE_PRINCIPAL,
        actor_id=ACTOR,
        tenant_id=TENANT,
    )
    assert len(pending) == 1
    assert pending[0]["call_id"] == "golden-call-write"
    assert pending[0]["tool_id"] == "repo.write"
    assert len(pending[0]["arguments_digest"]) == 64
    assert effects == []

    approval = service.approve_tool_call(
        EXECUTION_ID,
        verified_service_principal=SERVICE_PRINCIPAL,
        actor_id=ACTOR,
        tenant_id=TENANT,
        call_id=pending[0]["call_id"],
        tool_id=pending[0]["tool_id"],
        arguments_digest=pending[0]["arguments_digest"],
        idempotency_key="golden-approval-1",
        expires_at=min(
            command.delegated_authority.expires_at,
            command.operation.deadline,
        ) - timedelta(seconds=1),
    )
    await coordinator.ensure_execution(EXECUTION_ID)
    result = await _wait_result(service, EXECUTION_ID)

    assert result.status == "completed"
    assert result.final_output == (
        "Atlas was confirmed from retrieval evidence and written."
    )
    assert result.verification_receipt["outcome"] == "verified"
    assert result.usage["model_turns"] == 2
    assert result.usage["tool_calls"] == 1
    assert len(result.tool_receipts) == 1
    assert effects == [approval.approval_ref]

    assert len(provider.requests) == 2
    first = provider.requests[0]
    second = provider.requests[1]
    assert result.tool_receipts[0] in second.prompt
    assert "artifact:golden-readme" in second.prompt
    assert first.context_id == context.context_id
    assert first.context_digest == context.context_digest
    assert first.context_source_snapshot == context.source_snapshot
    assert first.context_compiler_version == context.compiler_version
    assert first.tools[0].tool_id == "repo.write"
    assert any(
        "The canonical project codename is Atlas." in message.content
        for message in first.history
    )

    events = service.events(
        EXECUTION_ID,
        verified_service_principal=SERVICE_PRINCIPAL,
        actor_id=ACTOR,
        tenant_id=TENANT,
    )
    assert any(
        event["type"] == "execution.result"
        for event in events["events"]
    )
    await coordinator.shutdown()


def test_retrieval_tenant_ambiguity_fails_before_compilation() -> None:
    ambiguous = RetrievedMemory(
        item_id="retrieval-cross-tenant",
        content="Do not leak this tenant data.",
        metadata={
            "tenant_id": "tenant-other",
            "data_class": "confidential",
            "purpose": PURPOSE,
            "created_at": CREATED.isoformat(),
        },
        source_repository="other-repo",
        relevance=1.0,
    )

    with pytest.raises(PermissionError, match="tenant mismatch"):
        retrieval_segment(
            ambiguous,
            tenant_id=TENANT,
            purpose=PURPOSE,
        )
