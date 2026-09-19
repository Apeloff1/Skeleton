"""Durable pre-execution obligation catalog for AI shell recovery.

Execution-attempt records are keyed by a known attempt/session. They do not by
themselves provide a globally enumerable set of executions that a restarted
worker must account for. This module closes that discovery gap.

Before a sealed execution may cross the process boundary, the service appends a
registration to an immutable CAS chain. The mutable obligation state is then
created from that committed registration. If a worker crashes between those
steps, a fresh reader reconstructs REGISTERED state from the catalog entry.

The catalog is evidence/discovery, not process authority.
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
from skeleton.shells.ai.execution_attempt import AIExecutionAttempt
from skeleton.shells.ai.finalization_state import (
    AIExecutionFinalization,
    FinalizationPhase,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend


GENESIS_HASH = "0" * 64


def _digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be 64 characters")
    return value.lower()


def _bounded_id(name: str, value: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"invalid {name}")
    return value


@dataclass(frozen=True)
class ExecutionObligationCatalogHead:
    sequence: int
    root_hash: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError("obligation catalog sequence must be non-negative")
        object.__setattr__(
            self,
            "root_hash",
            _digest("root_hash", self.root_hash),
        )
        if self.sequence == 0 and self.root_hash != GENESIS_HASH:
            raise ValueError("empty obligation catalog must use genesis root")
        if self.sequence > 0 and self.root_hash == GENESIS_HASH:
            raise ValueError("non-empty obligation catalog may not use genesis root")

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "root_hash": self.root_hash,
        }


@dataclass(frozen=True)
class ExecutionObligationCatalogEntry:
    sequence: int
    previous_hash: str
    node_hash: str
    obligation_id: str
    session_id: str
    principal: str
    plan_fingerprint: str
    execution_seal_id: str
    runtime_trust_digest: str
    release_evidence_digest: str
    created_at: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError("obligation catalog sequence must be positive")
        object.__setattr__(
            self,
            "previous_hash",
            _digest("previous_hash", self.previous_hash),
        )
        object.__setattr__(
            self,
            "node_hash",
            _digest("node_hash", self.node_hash),
        )
        for name in (
            "obligation_id",
            "session_id",
            "principal",
            "execution_seal_id",
        ):
            _bounded_id(name, getattr(self, name))
        object.__setattr__(
            self,
            "plan_fingerprint",
            _digest("plan_fingerprint", self.plan_fingerprint),
        )
        object.__setattr__(
            self,
            "runtime_trust_digest",
            _digest(
                "runtime_trust_digest",
                self.runtime_trust_digest,
                optional=True,
            ),
        )
        object.__setattr__(
            self,
            "release_evidence_digest",
            _digest(
                "release_evidence_digest",
                self.release_evidence_digest,
                optional=True,
            ),
        )
        if (
            isinstance(self.created_at, bool)
            or not isinstance(self.created_at, (int, float))
            or not math.isfinite(float(self.created_at))
            or float(self.created_at) < 0.0
        ):
            raise ValueError("obligation catalog created_at invalid")
        object.__setattr__(self, "created_at", float(self.created_at))

    def authority_dict(self) -> dict[str, object]:
        return {
            "obligation_id": self.obligation_id,
            "session_id": self.session_id,
            "principal": self.principal,
            "plan_fingerprint": self.plan_fingerprint,
            "execution_seal_id": self.execution_seal_id,
            "runtime_trust_digest": self.runtime_trust_digest,
            "release_evidence_digest": self.release_evidence_digest,
        }

    @property
    def authority_digest(self) -> str:
        raw = json.dumps(
            self.authority_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "previous_hash": self.previous_hash,
            "node_hash": self.node_hash,
            **self.authority_dict(),
            "authority_digest": self.authority_digest,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ExecutionObligationCatalogIndex:
    obligation_id: str
    sequence: int
    node_hash: str
    authority_digest: str

    def __post_init__(self) -> None:
        _bounded_id("obligation_id", self.obligation_id)
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError("obligation index sequence must be positive")
        object.__setattr__(
            self,
            "node_hash",
            _digest("node_hash", self.node_hash),
        )
        object.__setattr__(
            self,
            "authority_digest",
            _digest("authority_digest", self.authority_digest),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "obligation_id": self.obligation_id,
            "sequence": self.sequence,
            "node_hash": self.node_hash,
            "authority_digest": self.authority_digest,
        }


class ExecutionObligationState(str, Enum):
    REGISTERED = "registered"
    ATTEMPT_BOUND = "attempt_bound"
    FINALIZED = "finalized"
    RETIRED = "retired"


@dataclass(frozen=True)
class AIExecutionObligation:
    schema_version: int
    obligation_id: str
    session_id: str
    principal: str
    plan_fingerprint: str
    execution_seal_id: str
    state: ExecutionObligationState
    created_at: float
    updated_at: float
    runtime_trust_digest: str = ""
    release_evidence_digest: str = ""
    attempt_authority_digest: str = ""
    attempt_state: str = ""
    terminal_evidence_digest: str = ""
    finalization_id: str = ""
    finalization_digest: str = ""
    retirement_proof_digest: str = ""
    retirement_reason: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported execution obligation schema")
        for name in (
            "obligation_id",
            "session_id",
            "principal",
            "execution_seal_id",
        ):
            _bounded_id(name, getattr(self, name))
        object.__setattr__(
            self,
            "plan_fingerprint",
            _digest("plan_fingerprint", self.plan_fingerprint),
        )
        object.__setattr__(
            self,
            "state",
            ExecutionObligationState(self.state),
        )
        for name in (
            "runtime_trust_digest",
            "release_evidence_digest",
            "attempt_authority_digest",
            "terminal_evidence_digest",
            "finalization_digest",
            "retirement_proof_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name), optional=True),
            )
        for name in ("created_at", "updated_at"):
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
            raise ValueError("execution obligation updated_at precedes creation")
        if len(self.attempt_state) > 64:
            raise ValueError("attempt_state too long")
        if len(self.finalization_id) > 256:
            raise ValueError("finalization_id too long")
        if len(self.retirement_reason) > 2048:
            raise ValueError("retirement_reason too long")

        if self.state is ExecutionObligationState.REGISTERED:
            if (
                self.attempt_authority_digest
                or self.attempt_state
                or self.terminal_evidence_digest
                or self.finalization_id
                or self.finalization_digest
                or self.retirement_proof_digest
                or self.retirement_reason
            ):
                raise ValueError(
                    "registered obligation may not carry downstream evidence"
                )
        elif self.state is ExecutionObligationState.ATTEMPT_BOUND:
            if not self.attempt_authority_digest or not self.attempt_state:
                raise ValueError("attempt-bound obligation needs attempt evidence")
            if self.finalization_id or self.finalization_digest:
                raise ValueError("attempt-bound obligation may not carry finalization")
            if self.retirement_proof_digest or self.retirement_reason:
                raise ValueError("attempt-bound obligation may not carry retirement")
        elif self.state is ExecutionObligationState.FINALIZED:
            if (
                not self.attempt_authority_digest
                or not self.attempt_state
                or not self.terminal_evidence_digest
                or not self.finalization_id
                or not self.finalization_digest
            ):
                raise ValueError(
                    "finalized obligation requires attempt, terminal, and finalization evidence"
                )
            if self.retirement_proof_digest or self.retirement_reason:
                raise ValueError("finalized obligation may not carry retirement")
        elif self.state is ExecutionObligationState.RETIRED:
            if not self.retirement_proof_digest or not self.retirement_reason:
                raise ValueError("retired obligation requires proof and reason")
            if self.finalization_id or self.finalization_digest:
                raise ValueError("retired obligation may not carry finalization")

    def authority_dict(self) -> dict[str, object]:
        return {
            "obligation_id": self.obligation_id,
            "session_id": self.session_id,
            "principal": self.principal,
            "plan_fingerprint": self.plan_fingerprint,
            "execution_seal_id": self.execution_seal_id,
            "runtime_trust_digest": self.runtime_trust_digest,
            "release_evidence_digest": self.release_evidence_digest,
        }

    @property
    def authority_digest(self) -> str:
        raw = json.dumps(
            self.authority_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def terminal(self) -> bool:
        return self.state in {
            ExecutionObligationState.FINALIZED,
            ExecutionObligationState.RETIRED,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            **self.authority_dict(),
            "authority_digest": self.authority_digest,
            "state": self.state.value,
            "terminal": self.terminal,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "attempt_authority_digest": self.attempt_authority_digest,
            "attempt_state": self.attempt_state,
            "terminal_evidence_digest": self.terminal_evidence_digest,
            "finalization_id": self.finalization_id,
            "finalization_digest": self.finalization_digest,
            "retirement_proof_digest": self.retirement_proof_digest,
            "retirement_reason": self.retirement_reason,
        }


@dataclass(frozen=True)
class StoredExecutionObligation:
    revision: int
    obligation: AIExecutionObligation

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError("execution obligation revision must be positive")


class ExecutionObligationConflict(RuntimeError):
    pass


class ExecutionObligationCorruption(RuntimeError):
    pass


class AIExecutionObligationStore:
    """Globally discoverable execution obligations with CAS state transitions."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = "shell-ai-execution-obligation",
        max_obligations: int = 100_000,
        max_retries: int = 32,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(backend, VersionedStateBackend):
            raise TypeError("backend must satisfy VersionedStateBackend")
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid execution obligation namespace")
        if (
            isinstance(max_obligations, bool)
            or not isinstance(max_obligations, int)
            or max_obligations <= 0
        ):
            raise ValueError("max_obligations must be positive")
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or not 1 <= max_retries <= 128
        ):
            raise ValueError("max_retries outside supported range")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.backend = backend
        self.namespace = namespace
        self.max_obligations = max_obligations
        self.max_retries = max_retries
        self._clock = clock

    @staticmethod
    def _node_key(node_hash: str) -> str:
        return "node:" + _digest("node_hash", node_hash)

    @staticmethod
    def _index_key(obligation_id: str) -> str:
        _bounded_id("obligation_id", obligation_id)
        return "index:" + hashlib.sha256(obligation_id.encode()).hexdigest()

    @staticmethod
    def _state_key(obligation_id: str) -> str:
        _bounded_id("obligation_id", obligation_id)
        return "state:" + hashlib.sha256(obligation_id.encode()).hexdigest()

    @staticmethod
    def _node_hash(
        previous_hash: str,
        sequence: int,
        *,
        obligation_id: str,
        session_id: str,
        principal: str,
        plan_fingerprint: str,
        execution_seal_id: str,
        runtime_trust_digest: str,
        release_evidence_digest: str,
        created_at: float,
    ) -> str:
        raw = json.dumps(
            {
                "previous_hash": previous_hash,
                "sequence": sequence,
                "obligation_id": obligation_id,
                "session_id": session_id,
                "principal": principal,
                "plan_fingerprint": plan_fingerprint,
                "execution_seal_id": execution_seal_id,
                "runtime_trust_digest": runtime_trust_digest,
                "release_evidence_digest": release_evidence_digest,
                "created_at": created_at,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def _head_revision(
        self,
    ) -> tuple[int, ExecutionObligationCatalogHead]:
        record = self.backend.get(self.namespace, "head")
        if record is None:
            return 0, ExecutionObligationCatalogHead(0, GENESIS_HASH)
        if not isinstance(record.value, ExecutionObligationCatalogHead):
            raise ExecutionObligationCorruption(
                "execution obligation catalog head type mismatch"
            )
        return record.revision, record.value

    def head(self) -> ExecutionObligationCatalogHead:
        return self._head_revision()[1]

    def get_node(
        self,
        node_hash: str,
    ) -> ExecutionObligationCatalogEntry:
        node_hash = _digest("node_hash", node_hash)
        record = self.backend.get(
            self.namespace,
            self._node_key(node_hash),
        )
        if record is None:
            raise ExecutionObligationCorruption(
                "execution obligation catalog node is missing"
            )
        if not isinstance(record.value, ExecutionObligationCatalogEntry):
            raise ExecutionObligationCorruption(
                "execution obligation catalog node type mismatch"
            )
        item = record.value
        expected = self._node_hash(
            item.previous_hash,
            item.sequence,
            obligation_id=item.obligation_id,
            session_id=item.session_id,
            principal=item.principal,
            plan_fingerprint=item.plan_fingerprint,
            execution_seal_id=item.execution_seal_id,
            runtime_trust_digest=item.runtime_trust_digest,
            release_evidence_digest=item.release_evidence_digest,
            created_at=item.created_at,
        )
        if expected != item.node_hash:
            raise ExecutionObligationCorruption(
                "execution obligation catalog node digest mismatch"
            )
        if item.node_hash != node_hash:
            raise ExecutionObligationCorruption(
                "execution obligation catalog node key/hash mismatch"
            )
        return item

    def snapshot(self) -> tuple[ExecutionObligationCatalogEntry, ...]:
        head = self.head()
        if head.sequence == 0:
            return ()
        reverse: list[ExecutionObligationCatalogEntry] = []
        current_hash = head.root_hash
        expected_sequence = head.sequence
        seen: set[str] = set()
        while current_hash != GENESIS_HASH:
            if current_hash in seen:
                raise ExecutionObligationCorruption(
                    "execution obligation catalog contains a cycle"
                )
            seen.add(current_hash)
            item = self.get_node(current_hash)
            if item.sequence != expected_sequence:
                raise ExecutionObligationCorruption(
                    "execution obligation catalog sequence is not contiguous"
                )
            reverse.append(item)
            current_hash = item.previous_hash
            expected_sequence -= 1
            if expected_sequence < 0:
                raise ExecutionObligationCorruption(
                    "execution obligation catalog sequence underflow"
                )
        if expected_sequence != 0:
            raise ExecutionObligationCorruption(
                "execution obligation catalog terminated before genesis"
            )
        values = tuple(reversed(reverse))
        if len(values) != head.sequence:
            raise ExecutionObligationCorruption(
                "execution obligation catalog length differs from head"
            )
        return values

    def verify(self) -> bool:
        try:
            values = self.snapshot()
            head = self.head()
        except Exception:
            return False
        previous = GENESIS_HASH
        for sequence, item in enumerate(values, start=1):
            if item.sequence != sequence or item.previous_hash != previous:
                return False
            expected = self._node_hash(
                previous,
                sequence,
                obligation_id=item.obligation_id,
                session_id=item.session_id,
                principal=item.principal,
                plan_fingerprint=item.plan_fingerprint,
                execution_seal_id=item.execution_seal_id,
                runtime_trust_digest=item.runtime_trust_digest,
                release_evidence_digest=item.release_evidence_digest,
                created_at=item.created_at,
            )
            if expected != item.node_hash:
                return False
            previous = item.node_hash
        return (
            head.sequence == len(values)
            and head.root_hash == (previous if values else GENESIS_HASH)
        )

    def root_hash(self) -> str:
        return self.head().root_hash

    def length(self) -> int:
        return self.head().sequence

    def _put_node(self, item: ExecutionObligationCatalogEntry) -> None:
        key = self._node_key(item.node_hash)
        existing = self.backend.get(self.namespace, key)
        if existing is None:
            try:
                self.backend.put_if_absent(self.namespace, key, item)
                return
            except DistributedStateConflict:
                existing = self.backend.get(self.namespace, key)
                if existing is None:
                    raise
        if not isinstance(existing.value, ExecutionObligationCatalogEntry):
            raise ExecutionObligationCorruption(
                "execution obligation catalog node type mismatch"
            )
        if existing.value != item:
            raise ExecutionObligationCorruption(
                "execution obligation content-addressed node collision"
            )

    def _put_index(self, item: ExecutionObligationCatalogEntry) -> None:
        index = ExecutionObligationCatalogIndex(
            item.obligation_id,
            item.sequence,
            item.node_hash,
            item.authority_digest,
        )
        key = self._index_key(item.obligation_id)
        existing = self.backend.get(self.namespace, key)
        if existing is None:
            try:
                self.backend.put_if_absent(self.namespace, key, index)
                return
            except DistributedStateConflict:
                existing = self.backend.get(self.namespace, key)
                if existing is None:
                    raise
        if not isinstance(existing.value, ExecutionObligationCatalogIndex):
            raise ExecutionObligationCorruption(
                "execution obligation index type mismatch"
            )
        if existing.value != index:
            raise ExecutionObligationConflict(
                "obligation_id already binds different catalog authority"
            )

    def _find_entry(
        self,
        obligation_id: str,
    ) -> ExecutionObligationCatalogEntry | None:
        key = self._index_key(obligation_id)
        record = self.backend.get(self.namespace, key)
        if record is None:
            matches = tuple(
                item
                for item in self.snapshot()
                if item.obligation_id == obligation_id
            )
            if not matches:
                return None
            if len(matches) != 1:
                raise ExecutionObligationCorruption(
                    "obligation_id appears multiple times in committed catalog"
                )
            self._put_index(matches[0])
            record = self.backend.get(self.namespace, key)
            if record is None:
                raise ExecutionObligationCorruption(
                    "execution obligation index repair failed"
                )
        if not isinstance(record.value, ExecutionObligationCatalogIndex):
            raise ExecutionObligationCorruption(
                "execution obligation index type mismatch"
            )
        index = record.value
        item = self.get_node(index.node_hash)
        if (
            item.obligation_id != obligation_id
            or item.sequence != index.sequence
            or item.authority_digest != index.authority_digest
        ):
            raise ExecutionObligationCorruption(
                "execution obligation index/catalog mismatch"
            )
        if index.sequence > self.head().sequence:
            raise ExecutionObligationCorruption(
                "execution obligation index references uncommitted sequence"
            )
        committed = self.snapshot()[index.sequence - 1]
        if committed.node_hash != index.node_hash:
            raise ExecutionObligationCorruption(
                "execution obligation index references orphan node"
            )
        return item

    def _append_catalog(
        self,
        *,
        obligation_id: str,
        session_id: str,
        principal: str,
        plan_fingerprint: str,
        execution_seal_id: str,
        runtime_trust_digest: str,
        release_evidence_digest: str,
    ) -> ExecutionObligationCatalogEntry:
        obligation_id = _bounded_id("obligation_id", obligation_id)
        session_id = _bounded_id("session_id", session_id)
        principal = _bounded_id("principal", principal)
        execution_seal_id = _bounded_id("execution_seal_id", execution_seal_id)
        plan_fingerprint = _digest("plan_fingerprint", plan_fingerprint)
        runtime_trust_digest = _digest(
            "runtime_trust_digest",
            runtime_trust_digest,
            optional=True,
        )
        release_evidence_digest = _digest(
            "release_evidence_digest",
            release_evidence_digest,
            optional=True,
        )
        existing = self._find_entry(obligation_id)
        if existing is not None:
            supplied = {
                "session_id": session_id,
                "principal": principal,
                "plan_fingerprint": plan_fingerprint,
                "execution_seal_id": execution_seal_id,
                "runtime_trust_digest": runtime_trust_digest,
                "release_evidence_digest": release_evidence_digest,
            }
            for name, value in supplied.items():
                if getattr(existing, name) != value:
                    raise ExecutionObligationConflict(
                        f"existing execution obligation differs in {name}"
                    )
            return existing

        created_at = float(self._clock())
        if not math.isfinite(created_at) or created_at < 0:
            raise ValueError("execution obligation clock returned invalid time")
        for _ in range(self.max_retries):
            revision, head = self._head_revision()
            if head.sequence >= self.max_obligations:
                raise RuntimeError("execution obligation catalog capacity exhausted")
            sequence = head.sequence + 1
            node_hash = self._node_hash(
                head.root_hash,
                sequence,
                obligation_id=obligation_id,
                session_id=session_id,
                principal=principal,
                plan_fingerprint=plan_fingerprint,
                execution_seal_id=execution_seal_id,
                runtime_trust_digest=runtime_trust_digest,
                release_evidence_digest=release_evidence_digest,
                created_at=created_at,
            )
            item = ExecutionObligationCatalogEntry(
                sequence,
                head.root_hash,
                node_hash,
                obligation_id,
                session_id,
                principal,
                plan_fingerprint,
                execution_seal_id,
                runtime_trust_digest,
                release_evidence_digest,
                created_at,
            )
            self._put_node(item)
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    "head",
                    expected_revision=revision,
                    value=ExecutionObligationCatalogHead(sequence, node_hash),
                )
            except DistributedStateConflict:
                current_revision, current = self._head_revision()
                if (
                    current.sequence == sequence
                    and current.root_hash == node_hash
                    and current_revision >= revision
                ):
                    self._put_index(item)
                    return item
                continue
            self._put_index(item)
            return item
        raise ExecutionObligationConflict(
            "execution obligation catalog CAS retry bound exceeded"
        )

    @staticmethod
    def _from_entry(
        entry: ExecutionObligationCatalogEntry,
    ) -> AIExecutionObligation:
        return AIExecutionObligation(
            1,
            entry.obligation_id,
            entry.session_id,
            entry.principal,
            entry.plan_fingerprint,
            entry.execution_seal_id,
            ExecutionObligationState.REGISTERED,
            entry.created_at,
            entry.created_at,
            entry.runtime_trust_digest,
            entry.release_evidence_digest,
        )

    def register(
        self,
        *,
        obligation_id: str,
        session_id: str,
        principal: str,
        plan_fingerprint: str,
        execution_seal_id: str,
        runtime_trust_digest: str = "",
        release_evidence_digest: str = "",
    ) -> StoredExecutionObligation:
        entry = self._append_catalog(
            obligation_id=obligation_id,
            session_id=session_id,
            principal=principal,
            plan_fingerprint=plan_fingerprint,
            execution_seal_id=execution_seal_id,
            runtime_trust_digest=runtime_trust_digest,
            release_evidence_digest=release_evidence_digest,
        )
        initial = self._from_entry(entry)
        key = self._state_key(obligation_id)
        try:
            record = self.backend.put_if_absent(
                self.namespace,
                key,
                initial,
            )
            return StoredExecutionObligation(record.revision, initial)
        except DistributedStateConflict:
            current = self.current(obligation_id)
            if current is None:
                raise ExecutionObligationConflict(
                    "execution obligation state race lost without winner"
                )
            if current.obligation.authority_digest != initial.authority_digest:
                raise ExecutionObligationConflict(
                    "execution obligation state authority mismatch"
                )
            return current

    def current(
        self,
        obligation_id: str,
    ) -> StoredExecutionObligation | None:
        entry = self._find_entry(obligation_id)
        if entry is None:
            return None
        key = self._state_key(obligation_id)
        record = self.backend.get(self.namespace, key)
        if record is None:
            # Catalog commit precedes state creation. Recover a crash in that
            # narrow window by recreating the deterministic REGISTERED state.
            initial = self._from_entry(entry)
            try:
                record = self.backend.put_if_absent(
                    self.namespace,
                    key,
                    initial,
                )
            except DistributedStateConflict:
                record = self.backend.get(self.namespace, key)
                if record is None:
                    raise ExecutionObligationCorruption(
                        "execution obligation state repair failed"
                    )
        if not isinstance(record.value, AIExecutionObligation):
            raise ExecutionObligationCorruption(
                "execution obligation state type mismatch"
            )
        obligation = record.value
        if obligation.authority_digest != entry.authority_digest:
            raise ExecutionObligationCorruption(
                "execution obligation state/catalog authority mismatch"
            )
        return StoredExecutionObligation(record.revision, obligation)

    def obligations(
        self,
    ) -> tuple[StoredExecutionObligation, ...]:
        values: list[StoredExecutionObligation] = []
        for entry in self.snapshot():
            stored = self.current(entry.obligation_id)
            if stored is None:
                raise ExecutionObligationCorruption(
                    "cataloged execution obligation disappeared"
                )
            values.append(stored)
        return tuple(values)

    def _transition(
        self,
        supplied: AIExecutionObligation,
        updated: AIExecutionObligation,
        *,
        allowed_from: frozenset[ExecutionObligationState],
    ) -> StoredExecutionObligation:
        if supplied.authority_digest != updated.authority_digest:
            raise ExecutionObligationConflict(
                "execution obligation transition changes authority"
            )
        key = self._state_key(supplied.obligation_id)
        for _ in range(self.max_retries):
            record = self.backend.get(self.namespace, key)
            if record is None or not isinstance(
                record.value,
                AIExecutionObligation,
            ):
                raise ExecutionObligationConflict(
                    "execution obligation state is missing"
                )
            current = record.value
            if current.authority_digest != supplied.authority_digest:
                raise ExecutionObligationConflict(
                    "execution obligation authority drift"
                )
            if current == updated:
                return StoredExecutionObligation(record.revision, current)
            if current.state not in allowed_from:
                raise ExecutionObligationConflict(
                    "execution obligation cannot transition from "
                    f"{current.state.value} to {updated.state.value}"
                )
            try:
                stored = self.backend.compare_and_swap(
                    self.namespace,
                    key,
                    expected_revision=record.revision,
                    value=updated,
                )
                return StoredExecutionObligation(
                    stored.revision,
                    updated,
                )
            except DistributedStateConflict:
                continue
        raise ExecutionObligationConflict(
            "execution obligation transition CAS retry bound exceeded"
        )

    def sync_attempt(
        self,
        obligation_id: str,
        attempt: AIExecutionAttempt,
    ) -> StoredExecutionObligation:
        if not isinstance(attempt, AIExecutionAttempt):
            raise TypeError("attempt must be AIExecutionAttempt")
        current = self.current(obligation_id)
        if current is None:
            raise ExecutionObligationConflict(
                "execution obligation is missing"
            )
        obligation = current.obligation
        expected = (
            obligation.session_id == attempt.session_id
            and obligation.principal == attempt.principal
            and obligation.plan_fingerprint == attempt.plan_fingerprint
            and obligation.execution_seal_id == attempt.execution_seal_id
            and obligation.obligation_id == attempt.attempt_id
            and (
                not obligation.runtime_trust_digest
                or obligation.runtime_trust_digest == attempt.runtime_trust_digest
            )
            and (
                not obligation.release_evidence_digest
                or obligation.release_evidence_digest
                == attempt.release_evidence_digest
            )
        )
        if not expected:
            raise ExecutionObligationConflict(
                "execution attempt does not match obligation authority"
            )
        if obligation.state is ExecutionObligationState.FINALIZED:
            if obligation.attempt_authority_digest != attempt.authority_digest:
                raise ExecutionObligationConflict(
                    "finalized obligation attempt authority mismatch"
                )
            return current
        if obligation.state is ExecutionObligationState.RETIRED:
            raise ExecutionObligationConflict(
                "retired obligation may not bind execution attempt"
            )
        updated = replace(
            obligation,
            state=ExecutionObligationState.ATTEMPT_BOUND,
            updated_at=float(self._clock()),
            attempt_authority_digest=attempt.authority_digest,
            attempt_state=attempt.state.value,
            terminal_evidence_digest=attempt.terminal_evidence_digest,
        )
        return self._transition(
            obligation,
            updated,
            allowed_from=frozenset(
                {
                    ExecutionObligationState.REGISTERED,
                    ExecutionObligationState.ATTEMPT_BOUND,
                }
            ),
        )

    @staticmethod
    def _finalization_digest(
        finalization: AIExecutionFinalization,
    ) -> str:
        raw = json.dumps(
            finalization.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def finalize(
        self,
        obligation_id: str,
        finalization: AIExecutionFinalization,
    ) -> StoredExecutionObligation:
        if not isinstance(finalization, AIExecutionFinalization):
            raise TypeError("finalization must be AIExecutionFinalization")
        if finalization.phase is not FinalizationPhase.COMPLETE:
            raise ValueError("execution obligation requires complete finalization")
        current = self.current(obligation_id)
        if current is None:
            raise ExecutionObligationConflict(
                "execution obligation is missing"
            )
        obligation = current.obligation
        if obligation.state is ExecutionObligationState.RETIRED:
            raise ExecutionObligationConflict(
                "retired obligation may not be finalized"
            )
        if obligation.state is ExecutionObligationState.REGISTERED:
            raise ExecutionObligationConflict(
                "execution obligation must bind attempt before finalization"
            )
        if (
            finalization.session_id != obligation.session_id
            or finalization.execution_attempt_id != obligation.obligation_id
            or finalization.execution_attempt_authority_digest
            != obligation.attempt_authority_digest
        ):
            raise ExecutionObligationConflict(
                "finalization does not match execution obligation"
            )
        if (
            obligation.terminal_evidence_digest
            and finalization.provenance_digest
            != obligation.terminal_evidence_digest
        ):
            raise ExecutionObligationConflict(
                "finalization provenance differs from attempt terminal evidence"
            )
        digest = self._finalization_digest(finalization)
        updated = replace(
            obligation,
            state=ExecutionObligationState.FINALIZED,
            updated_at=float(self._clock()),
            finalization_id=finalization.finalization_id,
            finalization_digest=digest,
            terminal_evidence_digest=finalization.provenance_digest,
        )
        return self._transition(
            obligation,
            updated,
            allowed_from=frozenset(
                {
                    ExecutionObligationState.ATTEMPT_BOUND,
                    ExecutionObligationState.FINALIZED,
                }
            ),
        )

    def retire(
        self,
        obligation_id: str,
        *,
        proof_digest: str,
        reason: str,
    ) -> StoredExecutionObligation:
        proof_digest = _digest("proof_digest", proof_digest)
        if not reason or len(reason) > 2048:
            raise ValueError("retirement reason is required")
        current = self.current(obligation_id)
        if current is None:
            raise ExecutionObligationConflict(
                "execution obligation is missing"
            )
        obligation = current.obligation
        if obligation.state is ExecutionObligationState.FINALIZED:
            raise ExecutionObligationConflict(
                "finalized obligation may not be retired"
            )
        updated = replace(
            obligation,
            state=ExecutionObligationState.RETIRED,
            updated_at=float(self._clock()),
            retirement_proof_digest=proof_digest,
            retirement_reason=reason,
        )
        return self._transition(
            obligation,
            updated,
            allowed_from=frozenset(
                {
                    ExecutionObligationState.REGISTERED,
                    ExecutionObligationState.ATTEMPT_BOUND,
                    ExecutionObligationState.RETIRED,
                }
            ),
        )
