"""Governed durable-memory admission for verified evidence-generation results.

Memory is downstream state, not a second verifier. Only completed, digest-bound
native generation with explicit project custody may become a ProjectFact.
External evidence remains attributable and cannot cross tenant/project/trust
boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from skeleton.ai.project_memory import ProjectFact, ProjectMemory


class EvidenceMemoryError(ValueError):
    pass


def _digest(value: object) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise EvidenceMemoryError("memory evidence is not canonical encodable") from exc
    return sha256(raw).hexdigest()


@dataclass(frozen=True)
class GenerationMemoryEvidence:
    context_source_digest: str
    context_text_digest: str
    model_identity_digest: str
    prompt_sequence_digest: str
    runtime_request_digest: str
    output_digest: str
    replay_receipt_digest: str
    generated_text: str
    terminal_reason: str = "completed"

    def __post_init__(self) -> None:
        for name in (
            "context_source_digest", "context_text_digest", "model_identity_digest",
            "prompt_sequence_digest", "runtime_request_digest", "output_digest",
            "replay_receipt_digest",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise EvidenceMemoryError(f"invalid {name}")
        if not isinstance(self.generated_text, str):
            raise EvidenceMemoryError("generated_text must be a string")
        try:
            self.generated_text.encode("utf-8")
        except UnicodeError as exc:
            raise EvidenceMemoryError("generated_text is not valid UTF-8") from exc
        if self.terminal_reason != "completed":
            raise EvidenceMemoryError("only completed generation may enter durable memory")

    @property
    def evidence_digest(self) -> str:
        return _digest({
            "schema": "skeleton.ai.generation-memory-evidence.v1",
            "context_source_digest": self.context_source_digest,
            "context_text_digest": self.context_text_digest,
            "model_identity_digest": self.model_identity_digest,
            "prompt_sequence_digest": self.prompt_sequence_digest,
            "runtime_request_digest": self.runtime_request_digest,
            "output_digest": self.output_digest,
            "replay_receipt_digest": self.replay_receipt_digest,
            "generated_text_digest": sha256(self.generated_text.encode("utf-8")).hexdigest(),
            "terminal_reason": self.terminal_reason,
        })


@dataclass(frozen=True)
class MemoryAdmissionReceipt:
    fact_id: str
    source_id: str
    evidence_digest: str
    tenant_id: str
    project_id: str
    trust_class: str

    @property
    def digest(self) -> str:
        return _digest({"schema": "skeleton.ai.memory-admission.v1", **self.__dict__})


def admit_generation_memory(
    memory: ProjectMemory,
    evidence: GenerationMemoryEvidence,
    *,
    tenant_id: str,
    project_id: str,
    trust_class: str = "generated-evidence",
    supersedes: str | None = None,
) -> tuple[ProjectMemory, MemoryAdmissionReceipt]:
    if not isinstance(memory, ProjectMemory):
        raise EvidenceMemoryError("ProjectMemory required")
    if not isinstance(evidence, GenerationMemoryEvidence):
        raise EvidenceMemoryError("GenerationMemoryEvidence required")
    if (tenant_id, project_id, trust_class) != (
        memory.tenant_id, memory.project_id, memory.trust_class
    ):
        raise EvidenceMemoryError("memory custody boundary mismatch")
    source_id = evidence.evidence_digest
    fact_id = _digest({
        "schema": "skeleton.ai.generated-project-fact.v1",
        "tenant_id": tenant_id,
        "project_id": project_id,
        "trust_class": trust_class,
        "source_id": source_id,
        "output_digest": evidence.output_digest,
        "value_digest": sha256(evidence.generated_text.encode("utf-8")).hexdigest(),
        "supersedes": supersedes,
    })
    fact = ProjectFact(
        fact_id, tenant_id, project_id, trust_class,
        evidence.generated_text, source_id, supersedes,
    )
    try:
        updated = memory.add(fact)
    except (ValueError, PermissionError) as exc:
        raise EvidenceMemoryError("project memory rejected generated evidence") from exc
    return updated, MemoryAdmissionReceipt(
        fact_id, source_id, evidence.evidence_digest,
        tenant_id, project_id, trust_class,
    )


__all__ = [
    "EvidenceMemoryError", "GenerationMemoryEvidence", "MemoryAdmissionReceipt",
    "admit_generation_memory",
]
