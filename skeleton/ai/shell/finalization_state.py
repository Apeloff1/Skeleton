"""Durable restart state for terminal AI execution evidence finalization.

A child process may finish successfully and the worker may still crash before
all recovery/audit evidence is committed.  This module records how far the
post-execution evidence pipeline progressed so restart can resume without
guessing whether the process itself should run again.

The record is evidence coordination only.  It never authorizes shell
execution.  Execution authority remains the signed execution seal, approval
layers, runtime trust, and optional execution fence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.store_protocol import VersionedStateBackend


class FinalizationPhase(str, Enum):
    STARTED = "started"
    SESSION_EVIDENCE = "session_evidence"
    CHECKPOINTED = "checkpointed"
    ANCHORED = "anchored"
    WITNESSED = "witnessed"
    SIGNED = "signed"
    COMPLETE = "complete"


_PHASE_ORDER = {
    FinalizationPhase.STARTED: 0,
    FinalizationPhase.SESSION_EVIDENCE: 10,
    FinalizationPhase.CHECKPOINTED: 20,
    FinalizationPhase.ANCHORED: 30,
    FinalizationPhase.WITNESSED: 40,
    FinalizationPhase.SIGNED: 50,
    FinalizationPhase.COMPLETE: 60,
}


class FinalizationRecovery(str, Enum):
    RESUME = "resume"
    VERIFY_ANCHOR = "verify_anchor"
    VERIFY_WITNESS = "verify_witness"
    VERIFY_SIGNED_EVIDENCE = "verify_signed_evidence"
    COMPLETE = "complete"


def _digest(name: str, value: str, *, optional: bool = False) -> str:
    if optional and not value:
        return ""
    if len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    # Digest values are opaque 64-character authority tokens; production

    # hashes are hexadecimal, while deterministic test/adapter sentinels may

    # use the full string alphabet.
    return value.lower()


@dataclass(frozen=True)
class AIExecutionFinalization:
    schema_version: int
    finalization_id: str
    session_id: str
    provenance_digest: str
    phase: FinalizationPhase
    created_at: float
    updated_at: float
    execution_attempt_id: str = ""
    execution_attempt_authority_digest: str = ""
    runtime_trust_digest: str = ""
    release_evidence_digest: str = ""
    require_recovery_checkpoint: bool = False
    require_witness: bool = False
    require_signed_evidence: bool = False
    session_evidence_digest: str = ""
    recovery_checkpoint_digest: str = ""
    audit_anchor_digest: str = ""
    audit_chain_node_hash: str = ""
    audit_root: str = ""
    audit_witness_digest: str = ""
    audit_witness_sequence: int | None = None
    execution_evidence_digest: str = ""
    execution_evidence_chain_node_hash: str = ""
    error_count: int = 0
    last_error_type: str = ""
    last_error_at: float = 0.0

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported execution finalization schema")
        if not self.finalization_id or len(self.finalization_id) > 256:
            raise ValueError("invalid finalization_id")
        if not self.session_id or len(self.session_id) > 160:
            raise ValueError("invalid finalization session_id")
        object.__setattr__(self, "phase", FinalizationPhase(self.phase))
        object.__setattr__(
            self,
            "provenance_digest",
            _digest("provenance_digest", self.provenance_digest),
        )
        for name in (
            "execution_attempt_authority_digest",
            "runtime_trust_digest",
            "release_evidence_digest",
            "session_evidence_digest",
            "recovery_checkpoint_digest",
            "audit_anchor_digest",
            "audit_chain_node_hash",
            "audit_root",
            "audit_witness_digest",
            "execution_evidence_digest",
            "execution_evidence_chain_node_hash",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name), optional=True),
            )
        for name in (
            "require_recovery_checkpoint",
            "require_witness",
            "require_signed_evidence",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")
        if len(self.execution_attempt_id) > 256:
            raise ValueError("execution_attempt_id too long")
        if bool(self.execution_attempt_id) != bool(
            self.execution_attempt_authority_digest
        ):
            raise ValueError(
                "execution attempt identity and authority digest must be paired"
            )
        if self.audit_witness_sequence is not None and (
            isinstance(self.audit_witness_sequence, bool)
            or not isinstance(self.audit_witness_sequence, int)
            or self.audit_witness_sequence <= 0
        ):
            raise ValueError("audit_witness_sequence must be positive")
        if bool(self.audit_witness_digest) != (
            self.audit_witness_sequence is not None
        ):
            raise ValueError(
                "audit witness digest and sequence must be paired"
            )
        for name in ("created_at", "updated_at", "last_error_at"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(f"{name} must be finite and non-negative")
            object.__setattr__(self, name, float(value))
        if self.updated_at < self.created_at:
            raise ValueError("finalization updated_at precedes creation")
        if self.last_error_at and self.last_error_at < self.created_at:
            raise ValueError("finalization last_error_at precedes creation")
        if (
            isinstance(self.error_count, bool)
            or not isinstance(self.error_count, int)
            or self.error_count < 0
        ):
            raise ValueError("error_count must be non-negative integer")
        if len(self.last_error_type) > 256:
            raise ValueError("last_error_type too long")
        if bool(self.last_error_type) != bool(self.error_count):
            raise ValueError(
                "last_error_type and error_count must be configured together"
            )
        if self.error_count and self.last_error_at <= 0:
            raise ValueError("recorded finalization error requires timestamp")
        self._validate_phase_evidence()

    def _validate_phase_evidence(self) -> None:
        order = _PHASE_ORDER[self.phase]

        # Report the evidence specific to the requested phase before inherited
        # prerequisites. This keeps failures actionable: a witnessed/signed
        # transition must say which witness/signature evidence is absent rather
        # than being masked by an earlier anchor prerequisite.
        if self.phase is FinalizationPhase.WITNESSED:
            if not self.audit_witness_digest:
                raise ValueError(
                    "witnessed phase requires audit witness evidence"
                )
        if self.phase is FinalizationPhase.SIGNED:
            if not self.execution_evidence_digest:
                raise ValueError(
                    "signed phase requires execution evidence digest"
                )
            if not self.execution_evidence_chain_node_hash:
                raise ValueError(
                    "signed phase requires execution evidence chain node"
                )

        if order >= _PHASE_ORDER[FinalizationPhase.SESSION_EVIDENCE]:
            if not self.session_evidence_digest:
                raise ValueError(
                    "session evidence phase requires session_evidence_digest"
                )
        if order >= _PHASE_ORDER[FinalizationPhase.CHECKPOINTED]:
            if not self.recovery_checkpoint_digest:
                raise ValueError(
                    "checkpointed phase requires recovery_checkpoint_digest"
                )
        if order >= _PHASE_ORDER[FinalizationPhase.ANCHORED]:
            if (
                not self.audit_anchor_digest
                or not self.audit_chain_node_hash
                or not self.audit_root
            ):
                raise ValueError(
                    "anchored phase requires audit anchor, chain node, and root"
                )
        if self.phase is FinalizationPhase.COMPLETE:
            if not self.audit_anchor_digest:
                raise ValueError("complete finalization requires audit anchor")
            if (
                self.require_recovery_checkpoint
                and not self.recovery_checkpoint_digest
            ):
                raise ValueError(
                    "complete finalization requires recovery checkpoint"
                )
            if self.require_witness and not self.audit_witness_digest:
                raise ValueError(
                    "complete finalization requires audit witness"
                )
            if (
                self.require_signed_evidence
                and not self.execution_evidence_digest
            ):
                raise ValueError(
                    "complete finalization requires signed execution evidence"
                )

    @classmethod
    def derive_id(
        cls,
        *,
        session_id: str,
        provenance_digest: str,
        execution_attempt_id: str = "",
    ) -> str:
        if not session_id:
            raise ValueError("session_id is required")
        provenance_digest = _digest(
            "provenance_digest",
            provenance_digest,
        )
        raw = json.dumps(
            {
                "session_id": session_id,
                "provenance_digest": provenance_digest,
                "execution_attempt_id": execution_attempt_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def binding_dict(self) -> dict[str, object]:
        return {
            "finalization_id": self.finalization_id,
            "session_id": self.session_id,
            "provenance_digest": self.provenance_digest,
            "execution_attempt_id": self.execution_attempt_id,
            "execution_attempt_authority_digest": (
                self.execution_attempt_authority_digest
            ),
            "runtime_trust_digest": self.runtime_trust_digest,
            "release_evidence_digest": self.release_evidence_digest,
            "require_recovery_checkpoint": (
                self.require_recovery_checkpoint
            ),
            "require_witness": self.require_witness,
            "require_signed_evidence": self.require_signed_evidence,
        }

    @property
    def binding_digest(self) -> str:
        raw = json.dumps(
            self.binding_dict,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def recovery(self) -> FinalizationRecovery:
        if self.phase is FinalizationPhase.COMPLETE:
            return FinalizationRecovery.COMPLETE
        if self.phase is FinalizationPhase.ANCHORED:
            return FinalizationRecovery.VERIFY_ANCHOR
        if self.phase is FinalizationPhase.WITNESSED:
            return FinalizationRecovery.VERIFY_WITNESS
        if self.phase is FinalizationPhase.SIGNED:
            return FinalizationRecovery.VERIFY_SIGNED_EVIDENCE
        return FinalizationRecovery.RESUME

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            **self.binding_dict,
            "binding_digest": self.binding_digest,
            "phase": self.phase.value,
            "recovery": self.recovery.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "session_evidence_digest": self.session_evidence_digest,
            "recovery_checkpoint_digest": self.recovery_checkpoint_digest,
            "audit_anchor_digest": self.audit_anchor_digest,
            "audit_chain_node_hash": self.audit_chain_node_hash,
            "audit_root": self.audit_root,
            "audit_witness_digest": self.audit_witness_digest,
            "audit_witness_sequence": self.audit_witness_sequence,
            "execution_evidence_digest": self.execution_evidence_digest,
            "execution_evidence_chain_node_hash": (
                self.execution_evidence_chain_node_hash
            ),
            "error_count": self.error_count,
            "last_error_type": self.last_error_type,
            "last_error_at": self.last_error_at,
        }


@dataclass(frozen=True)
class StoredExecutionFinalization:
    revision: int
    finalization: AIExecutionFinalization

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError("finalization revision must be positive")

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "finalization": self.finalization.to_dict(),
        }


class ExecutionFinalizationConflict(RuntimeError):
    pass


class AIExecutionFinalizationStore:
    """CAS-backed monotonic finalization progress for one terminal execution."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = "shell-ai-execution-finalization",
        max_retries: int = 16,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid finalization namespace")
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or not 1 <= max_retries <= 64
        ):
            raise ValueError("max_retries outside supported range")
        self.backend = backend
        self.namespace = namespace
        self.max_retries = max_retries
        self._clock = clock

    @staticmethod
    def key(finalization_id: str) -> str:
        if not finalization_id or len(finalization_id) > 256:
            raise ValueError("invalid finalization_id")
        return "finalization:" + hashlib.sha256(
            finalization_id.encode()
        ).hexdigest()

    def reserve(
        self,
        *,
        session_id: str,
        provenance_digest: str,
        execution_attempt_id: str = "",
        execution_attempt_authority_digest: str = "",
        runtime_trust_digest: str = "",
        release_evidence_digest: str = "",
        require_recovery_checkpoint: bool = False,
        require_witness: bool = False,
        require_signed_evidence: bool = False,
        finalization_id: str = "",
    ) -> StoredExecutionFinalization:
        if not finalization_id:
            finalization_id = AIExecutionFinalization.derive_id(
                session_id=session_id,
                provenance_digest=provenance_digest,
                execution_attempt_id=execution_attempt_id,
            )
        now = self._clock()
        item = AIExecutionFinalization(
            1,
            finalization_id,
            session_id,
            provenance_digest,
            FinalizationPhase.STARTED,
            now,
            now,
            execution_attempt_id,
            execution_attempt_authority_digest,
            runtime_trust_digest,
            release_evidence_digest,
            require_recovery_checkpoint,
            require_witness,
            require_signed_evidence,
        )
        key = self.key(finalization_id)
        try:
            record = self.backend.put_if_absent(
                self.namespace,
                key,
                item,
            )
            return StoredExecutionFinalization(record.revision, item)
        except DistributedStateConflict as exc:
            current = self.current(finalization_id)
            if current is None:
                raise
            if current.finalization.binding_digest != item.binding_digest:
                raise ExecutionFinalizationConflict(
                    "finalization id already binds different execution"
                ) from exc
            return current

    def current(
        self,
        finalization_id: str,
    ) -> StoredExecutionFinalization | None:
        record = self.backend.get(
            self.namespace,
            self.key(finalization_id),
        )
        if record is None:
            return None
        if not isinstance(record.value, AIExecutionFinalization):
            raise RuntimeError("finalization backend value type mismatch")
        return StoredExecutionFinalization(record.revision, record.value)

    @staticmethod
    def _same_binding(
        expected: AIExecutionFinalization,
        current: AIExecutionFinalization,
    ) -> None:
        if expected.finalization_id != current.finalization_id:
            raise ExecutionFinalizationConflict(
                "finalization identity mismatch"
            )
        if expected.binding_digest != current.binding_digest:
            raise ExecutionFinalizationConflict(
                "finalization authority binding mismatch"
            )

    def advance(
        self,
        expected: AIExecutionFinalization,
        phase: FinalizationPhase,
        *,
        session_evidence_digest: str = "",
        recovery_checkpoint_digest: str = "",
        audit_anchor_digest: str = "",
        audit_chain_node_hash: str = "",
        audit_root: str = "",
        audit_witness_digest: str = "",
        audit_witness_sequence: int | None = None,
        execution_evidence_digest: str = "",
        execution_evidence_chain_node_hash: str = "",
    ) -> StoredExecutionFinalization:
        phase = FinalizationPhase(phase)
        for _ in range(self.max_retries):
            record = self.backend.get(
                self.namespace,
                self.key(expected.finalization_id),
            )
            if record is None or not isinstance(
                record.value,
                AIExecutionFinalization,
            ):
                raise ExecutionFinalizationConflict(
                    "finalization record is missing"
                )
            current = record.value
            self._same_binding(expected, current)
            if _PHASE_ORDER[phase] < _PHASE_ORDER[current.phase]:
                return StoredExecutionFinalization(
                    record.revision,
                    current,
                )

            supplied = {
                "session_evidence_digest": session_evidence_digest,
                "recovery_checkpoint_digest": recovery_checkpoint_digest,
                "audit_anchor_digest": audit_anchor_digest,
                "audit_chain_node_hash": audit_chain_node_hash,
                "audit_root": audit_root,
                "audit_witness_digest": audit_witness_digest,
                "audit_witness_sequence": audit_witness_sequence,
                "execution_evidence_digest": execution_evidence_digest,
                "execution_evidence_chain_node_hash": (
                    execution_evidence_chain_node_hash
                ),
            }
            if phase is current.phase:
                conflict = False
                for name, value in supplied.items():
                    if value in {"", None}:
                        continue
                    if getattr(current, name) != value:
                        conflict = True
                        break
                if conflict:
                    raise ExecutionFinalizationConflict(
                        "same finalization phase carries different evidence"
                    )
                return StoredExecutionFinalization(
                    record.revision,
                    current,
                )

            updates = {
                "session_evidence_digest": (
                    session_evidence_digest
                    or current.session_evidence_digest
                ),
                "recovery_checkpoint_digest": (
                    recovery_checkpoint_digest
                    or current.recovery_checkpoint_digest
                ),
                "audit_anchor_digest": (
                    audit_anchor_digest
                    or current.audit_anchor_digest
                ),
                "audit_chain_node_hash": (
                    audit_chain_node_hash
                    or current.audit_chain_node_hash
                ),
                "audit_root": (
                    audit_root
                    or current.audit_root
                ),
                "audit_witness_digest": (
                    audit_witness_digest
                    or current.audit_witness_digest
                ),
                "audit_witness_sequence": (
                    audit_witness_sequence
                    if audit_witness_sequence is not None
                    else current.audit_witness_sequence
                ),
                "execution_evidence_digest": (
                    execution_evidence_digest
                    or current.execution_evidence_digest
                ),
                "execution_evidence_chain_node_hash": (
                    execution_evidence_chain_node_hash
                    or current.execution_evidence_chain_node_hash
                ),
            }
            updated = replace(
                current,
                phase=phase,
                updated_at=self._clock(),
                **updates,
            )
            if current.phase is phase and current == updated:
                return StoredExecutionFinalization(
                    record.revision,
                    current,
                )
            try:
                stored = self.backend.compare_and_swap(
                    self.namespace,
                    self.key(expected.finalization_id),
                    expected_revision=record.revision,
                    value=updated,
                )
                return StoredExecutionFinalization(
                    stored.revision,
                    updated,
                )
            except DistributedStateConflict:
                continue
        raise ExecutionFinalizationConflict(
            "finalization phase CAS retry bound exceeded"
        )

    def note_error(
        self,
        expected: AIExecutionFinalization,
        exc: BaseException,
    ) -> StoredExecutionFinalization:
        error_type = type(exc).__name__
        if len(error_type) > 256:
            error_type = error_type[:256]
        for _ in range(self.max_retries):
            record = self.backend.get(
                self.namespace,
                self.key(expected.finalization_id),
            )
            if record is None or not isinstance(
                record.value,
                AIExecutionFinalization,
            ):
                raise ExecutionFinalizationConflict(
                    "finalization record is missing"
                )
            current = record.value
            self._same_binding(expected, current)
            updated = replace(
                current,
                updated_at=self._clock(),
                error_count=current.error_count + 1,
                last_error_type=error_type,
                last_error_at=self._clock(),
            )
            try:
                stored = self.backend.compare_and_swap(
                    self.namespace,
                    self.key(expected.finalization_id),
                    expected_revision=record.revision,
                    value=updated,
                )
                return StoredExecutionFinalization(
                    stored.revision,
                    updated,
                )
            except DistributedStateConflict:
                continue
        raise ExecutionFinalizationConflict(
            "finalization error-note CAS retry bound exceeded"
        )

    def require_complete(
        self,
        finalization_id: str,
    ) -> AIExecutionFinalization:
        current = self.current(finalization_id)
        if current is None:
            raise ExecutionFinalizationConflict(
                "finalization record is missing"
            )
        if current.finalization.phase is not FinalizationPhase.COMPLETE:
            raise ExecutionFinalizationConflict(
                f"finalization is not complete: "
                f"{current.finalization.phase.value}"
            )
        return current.finalization
