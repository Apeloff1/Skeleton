from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest

from skeleton.contracts.context import ContextBudget, ContextKind, ContextTrust
from skeleton.contracts.memory_record import (
    MemoryKind,
    MemoryRecord,
    MemoryState,
    memory_payload_digest,
)
from skeleton.context.compiler import ContextCompiler
from skeleton.context.skills_files import SkillSpec
from skeleton.context.sources import (
    artifact_segment,
    memory_record_segment,
    skill_instruction_segment,
    tool_manifest_segment,
)
from skeleton.skills.tool_contract import ToolManifest


NOW = datetime(2026, 9, 24, 1, 45, tzinfo=timezone.utc)


def _memory(*, tenant_id: str = "tenant-a", state: MemoryState = MemoryState.ACTIVE, expires_at=None):
    content = "canonical remembered fact"
    refs = ("source:conversation",)
    return MemoryRecord(
        memory_id=str(uuid4()),
        tenant_id=tenant_id,
        namespace="assistant",
        subject_id="subject-a",
        kind=MemoryKind.SEMANTIC,
        version=2,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW,
        idempotency_key="memory-write-1",
        payload_digest=memory_payload_digest(
            kind=MemoryKind.SEMANTIC,
            content=content,
            content_ref=None,
            provenance_refs=refs,
        ),
        content=content,
        provenance_refs=refs,
        state=state,
        expires_at=expires_at,
        data_class="confidential",
    )


def _budget() -> ContextBudget:
    return ContextBudget(
        max_context_tokens=400,
        reserved_output_tokens=40,
        reserved_tool_result_tokens=40,
        reserved_policy_tokens=60,
        safety_margin_tokens=10,
        max_segment_tokens=200,
        max_artifact_tokens=80,
        max_tool_result_tokens=80,
    )


def test_memory_adapter_preserves_authority_and_rejects_invalid_lifecycle():
    record = _memory()
    segment = memory_record_segment(
        record,
        tenant_id="tenant-a",
        purpose="chat",
        now=NOW,
    )
    assert segment.kind is ContextKind.MEMORY
    assert segment.trust_level is ContextTrust.AUTHORIZED_USER_DATA
    assert segment.source_id == record.memory_id
    assert segment.data_class == "confidential"
    assert "memory-payload:" + record.payload_digest in segment.provenance

    with pytest.raises(PermissionError, match="tenant"):
        memory_record_segment(record, tenant_id="tenant-b", purpose="chat", now=NOW)
    with pytest.raises(ValueError, match="tombstoned"):
        memory_record_segment(
            _memory(state=MemoryState.TOMBSTONED),
            tenant_id="tenant-a",
            purpose="chat",
            now=NOW,
        )
    with pytest.raises(ValueError, match="expired"):
        memory_record_segment(
            _memory(expires_at=NOW - timedelta(seconds=1)),
            tenant_id="tenant-a",
            purpose="chat",
            now=NOW,
        )


def test_artifact_adapter_is_untrusted_and_oversize_remains_compiler_bounded():
    segment = artifact_segment(
        artifact_id="artifact-1",
        content="x" * 600,
        tenant_id="tenant-a",
        purpose="chat",
        created_at=NOW,
        data_class="internal",
    )
    assert segment.kind is ContextKind.ARTIFACT
    assert segment.trust_level is ContextTrust.UNTRUSTED_EVIDENCE

    envelope = ContextCompiler().compile(
        operation_id=str(uuid4()),
        execution_id=str(uuid4()),
        turn_id=str(uuid4()),
        tenant_id="tenant-a",
        purpose="chat",
        budget=_budget(),
        segments=(segment,),
        compiled_at=NOW,
    )
    assert envelope.evidence_segments == ()
    assert dict(envelope.omission_reasons)[segment.segment_id] == "segment_limit_exceeded"


def test_tool_manifest_adapter_emits_deterministic_provider_neutral_schema():
    manifest = ToolManifest(
        tool_id="search.docs",
        version="1.2.0",
        description="Search approved documentation",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string", "maxLength": 200}},
            "required": ["query"],
            "additionalProperties": False,
        },
    )
    first = tool_manifest_segment(
        manifest,
        tenant_id="tenant-a",
        purpose="chat",
        created_at=NOW,
    )
    second = tool_manifest_segment(
        manifest,
        tenant_id="tenant-a",
        purpose="chat",
        created_at=NOW + timedelta(seconds=1),
    )
    assert first.segment_id == second.segment_id
    assert first.content_digest == second.content_digest
    payload = json.loads(first.content or "")
    assert payload["tool_id"] == "search.docs"
    assert payload["input_schema"] == dict(manifest.input_schema)
    assert first.trust_level is ContextTrust.TRUSTED_CONTROL
    assert first.source_type == "tool-registry"


def test_skill_adapter_is_trusted_control_but_keeps_versioned_source_identity():
    skill = SkillSpec(
        skill_id="repo-review",
        description="Review repository changes",
        source="registry-v3",
        instructions="Inspect changed files and report evidence.",
    )
    segment = skill_instruction_segment(
        skill,
        tenant_id="tenant-a",
        purpose="chat",
        created_at=NOW,
    )
    assert segment.kind is ContextKind.SKILL_INSTRUCTION
    assert segment.trust_level is ContextTrust.TRUSTED_CONTROL
    assert segment.source_id == "repo-review@registry-v3"
    assert segment.content == "Inspect changed files and report evidence."
