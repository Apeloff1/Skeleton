"""Governed staged memory writeback coordinator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import threading

from skeleton.artifact_plane.usage import ArtifactUsageMeter
from skeleton.contracts.memory_record import MemoryRecord, MemoryWriteProposal
from skeleton.intelligence.admission import AdmissionError
from skeleton.intelligence.admission_runtime import (
    AdmissionRuntime,
    AdmissionRuntimeError,
)
from skeleton.memory.policy import (
    MemoryPolicyEngine,
    MemoryPolicyResult,
    MemoryWriteDecision,
)
from skeleton.persistence.memory_repository import SQLiteMemoryRepository
from skeleton.vault.governance_registry import GovernanceRegistry
from skeleton.vault.lifecycle_adapters import SQLiteMemoryLifecycleAdapter


class MemoryWritebackError(RuntimeError):
    """Base governed writeback failure."""


class MemoryWriteDenied(MemoryWritebackError):
    """Policy denied or held a proposal before durable mutation."""


class MemoryStageConflict(MemoryWritebackError):
    """A proposal identity was reused with different content."""


@dataclass(frozen=True, slots=True)
class StagedMemoryWrite:
    proposal: MemoryWriteProposal
    policy: MemoryPolicyResult

    @property
    def proposal_id(self) -> str:
        return self.proposal.proposal_id


class GovernedMemoryWriter:
    """Policy-gated memory writer.

    Staging is side-effect free. Only commit may mutate the canonical
    repository, so model/retrieval code can create proposals without receiving
    storage authority.
    """

    def __init__(
        self,
        repository: SQLiteMemoryRepository,
        *,
        governance: GovernanceRegistry,
        policy: MemoryPolicyEngine | None = None,
        admission_runtime: AdmissionRuntime | None = None,
        purposes: tuple[str, ...] = (
            "model-inference",
            "retrieval-synthesis",
        ),
    ) -> None:
        if not isinstance(repository, SQLiteMemoryRepository):
            raise TypeError("repository must be SQLiteMemoryRepository")
        if not isinstance(governance, GovernanceRegistry):
            raise TypeError("governance must be GovernanceRegistry")
        if (
            admission_runtime is not None
            and not isinstance(admission_runtime, AdmissionRuntime)
        ):
            raise TypeError("admission_runtime must be AdmissionRuntime")
        normalized_purposes = tuple(
            dict.fromkeys(str(value).strip().lower() for value in purposes)
        )
        if not normalized_purposes or any(not value for value in normalized_purposes):
            raise ValueError("purposes must contain non-empty values")
        self.repository = repository
        self.governance = governance
        self.purposes = normalized_purposes
        self.policy = policy or MemoryPolicyEngine()
        self.admission_runtime = admission_runtime
        self._usage_meter = (
            None
            if admission_runtime is None
            else ArtifactUsageMeter(admission_runtime)
        )
        self._lock = threading.RLock()
        self._staged: dict[str, StagedMemoryWrite] = {}

    def stage(self, proposal: MemoryWriteProposal) -> StagedMemoryWrite:
        if not isinstance(proposal, MemoryWriteProposal):
            raise TypeError("proposal must be MemoryWriteProposal")
        result = self.policy.evaluate(proposal)
        staged = StagedMemoryWrite(proposal=proposal, policy=result)
        with self._lock:
            existing = self._staged.get(proposal.proposal_id)
            if existing is not None:
                if (
                    existing.proposal.payload_digest != proposal.payload_digest
                    or existing.proposal.idempotency_key != proposal.idempotency_key
                    or existing.proposal.target_memory_id != proposal.target_memory_id
                    or existing.proposal.expected_version != proposal.expected_version
                ):
                    raise MemoryStageConflict(
                        "proposal_id replayed with different write intent"
                    )
                return existing
            self._staged[proposal.proposal_id] = staged
            return staged

    @staticmethod
    def _proposal_storage_payload(
        proposal: MemoryWriteProposal,
    ) -> dict[str, object]:
        return {
            "schema_version": proposal.schema_version,
            "proposal_id": proposal.proposal_id,
            "tenant_id": proposal.tenant_id,
            "namespace": proposal.namespace,
            "subject_id": proposal.subject_id,
            "kind": proposal.kind.value,
            "idempotency_key": proposal.idempotency_key,
            "proposed_at": proposal.proposed_at.astimezone(
                timezone.utc
            ).isoformat(),
            "content": proposal.content,
            "content_ref": proposal.content_ref,
            "provenance_refs": list(proposal.provenance_refs),
            "source_operation_id": proposal.source_operation_id,
            "target_memory_id": proposal.target_memory_id,
            "expected_version": proposal.expected_version,
            "expires_at": (
                None
                if proposal.expires_at is None
                else proposal.expires_at.astimezone(
                    timezone.utc
                ).isoformat()
            ),
            "data_class": proposal.data_class,
        }

    def _meter_storage(
        self,
        proposal: MemoryWriteProposal,
        *,
        now: datetime | None,
    ) -> None:
        meter = self._usage_meter
        if meter is None:
            return
        operation_id = proposal.source_operation_id
        if operation_id is None:
            raise MemoryWritebackError(
                "admitted memory write requires source_operation_id"
            )
        payload = self._proposal_storage_payload(proposal)
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        instant = (
            datetime.now(timezone.utc)
            if now is None
            else now.astimezone(timezone.utc)
        )
        try:
            meter.meter_storage(
                operation_id,
                (
                    "memory:"
                    + proposal.tenant_id
                    + ":"
                    + proposal.namespace
                ),
                proposal.proposal_id,
                len(encoded),
                now_wall=instant.timestamp(),
            )
        except (AdmissionError, AdmissionRuntimeError) as exc:
            raise MemoryWritebackError(
                "memory write denied by resource admission"
            ) from exc

    def commit(
        self,
        proposal_id: str,
        *,
        review_approved: bool = False,
        now: datetime | None = None,
    ) -> MemoryRecord:
        key = str(proposal_id).strip()
        if not key:
            raise MemoryWritebackError("proposal_id is required")
        with self._lock:
            staged = self._staged.get(key)
            if staged is None:
                raise MemoryWritebackError("proposal is not staged")
            if staged.policy.decision is MemoryWriteDecision.DENY:
                raise MemoryWriteDenied(staged.policy.reason)
            if (
                staged.policy.decision is MemoryWriteDecision.REVIEW
                and not review_approved
            ):
                raise MemoryWriteDenied(staged.policy.reason)
            self._meter_storage(staged.proposal, now=now)
            record = self.repository.commit(staged.proposal, now=now)
            try:
                self.governance.reconcile_canonical_write(
                    "memory",
                    record_id=record.memory_id,
                    tenant_id=record.tenant_id,
                    source_ref=SQLiteMemoryLifecycleAdapter.source_ref(
                        record.namespace,
                        record.memory_id,
                    ),
                    data_class=record.data_class,
                    purposes=self.purposes,
                    deletion_targets=("memory",),
                    created_at=record.created_at.timestamp(),
                    retention_until=(
                        None
                        if record.expires_at is None
                        else record.expires_at.timestamp()
                    ),
                    exportable=True,
                )
            except Exception as exc:
                try:
                    self.repository.tombstone(
                        record.memory_id,
                        tenant_id=record.tenant_id,
                        namespace=record.namespace,
                        expected_version=record.version,
                        now=now,
                    )
                except Exception as tombstone_exc:
                    raise MemoryWritebackError(
                        "governance registration failed and memory could not be "
                        "tombstoned fail-closed"
                    ) from tombstone_exc
                raise MemoryWritebackError(
                    "governance registration failed; memory was tombstoned "
                    "fail-closed"
                ) from exc
            self._staged.pop(key, None)
            return record

    def discard(self, proposal_id: str) -> bool:
        with self._lock:
            return self._staged.pop(str(proposal_id), None) is not None

    def staged_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._staged))


__all__ = [
    "GovernedMemoryWriter",
    "MemoryStageConflict",
    "MemoryWriteDenied",
    "MemoryWritebackError",
    "StagedMemoryWrite",
]
