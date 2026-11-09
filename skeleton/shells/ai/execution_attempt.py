"""Durable execution-attempt ledger for crash-safe AI shell recovery.

Execution seals prove authorization and fenced leases prove which worker owns an
execution lane. Neither one records whether a worker had already begun crossing
the process-creation boundary when it crashed.

This ledger is evidence, not authority. A sealed execution records an immutable
binding, advances it with compare-and-swap immediately before process dispatch,
and records a terminal state afterward. A crash in BOUNDARY_ENTERED is
intentionally ambiguous and must never be auto-replayed.
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
from skeleton.shells.ai.execution_backend import AIPlanExecutionBackend
from skeleton.shells.ai.store_protocol import VersionedStateBackend
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.execution_plan import ExecutionPlan
from skeleton.shells.plan_executor import PlanExecutionReport


class ExecutionAttemptState(str, Enum):
    AUTHORIZED = "authorized"
    BOUNDARY_ENTERED = "boundary_entered"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABANDONED = "abandoned"


TERMINAL_ATTEMPT_STATES = frozenset(
    {
        ExecutionAttemptState.SUCCEEDED,
        ExecutionAttemptState.FAILED,
        ExecutionAttemptState.ABANDONED,
    }
)


class ExecutionAttemptRecovery(str, Enum):
    NOT_STARTED = "not_started"
    REQUIRE_VERIFICATION = "require_verification"
    TERMINAL_SUCCESS = "terminal_success"
    TERMINAL_FAILURE = "terminal_failure"
    ABANDONED = "abandoned"


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
class AIExecutionAttempt:
    schema_version: int
    attempt_id: str
    session_id: str
    principal: str
    worker_id: str
    plan_fingerprint: str
    execution_seal_id: str
    state: ExecutionAttemptState
    created_at: float
    updated_at: float
    execution_fence_digest: str = ""
    fencing_token: int | None = None
    runtime_trust_digest: str = ""
    release_evidence_digest: str = ""
    execution_backend_id: str = ""
    terminal_evidence_digest: str = ""
    error_type: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported execution attempt schema")
        for name in (
            "attempt_id",
            "session_id",
            "principal",
            "worker_id",
            "execution_seal_id",
        ):
            value = getattr(self, name)
            if not value or len(value) > 256:
                raise ValueError(f"invalid execution attempt {name}")
        object.__setattr__(self, "state", ExecutionAttemptState(self.state))
        object.__setattr__(
            self,
            "plan_fingerprint",
            _digest("plan_fingerprint", self.plan_fingerprint),
        )
        for name in (
            "execution_fence_digest",
            "runtime_trust_digest",
            "release_evidence_digest",
            "terminal_evidence_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name), optional=True),
            )
        if self.fencing_token is not None and (
            isinstance(self.fencing_token, bool)
            or not isinstance(self.fencing_token, int)
            or self.fencing_token <= 0
        ):
            raise ValueError("execution attempt fencing_token must be positive")
        if bool(self.execution_fence_digest) != (self.fencing_token is not None):
            raise ValueError(
                "execution fence digest and fencing token must be configured together"
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
            raise ValueError("execution attempt updated_at precedes creation")
        if len(self.execution_backend_id) > 256:
            raise ValueError("execution_backend_id too long")
        if len(self.error_type) > 256:
            raise ValueError("execution attempt error_type too long")
        if self.state is ExecutionAttemptState.SUCCEEDED:
            if not self.terminal_evidence_digest:
                raise ValueError(
                    "successful execution attempt requires terminal evidence"
                )
            if self.error_type:
                raise ValueError(
                    "successful execution attempt may not carry error_type"
                )
        if self.state is ExecutionAttemptState.FAILED and not self.error_type:
            raise ValueError("failed execution attempt requires error_type")
        if (
            self.state
            in {
                ExecutionAttemptState.AUTHORIZED,
                ExecutionAttemptState.BOUNDARY_ENTERED,
            }
            and (self.terminal_evidence_digest or self.error_type)
        ):
            raise ValueError(
                "non-terminal execution attempt may not carry terminal evidence"
            )

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_ATTEMPT_STATES

    @property
    def recovery(self) -> ExecutionAttemptRecovery:
        return {
            ExecutionAttemptState.AUTHORIZED: ExecutionAttemptRecovery.NOT_STARTED,
            ExecutionAttemptState.BOUNDARY_ENTERED: (
                ExecutionAttemptRecovery.REQUIRE_VERIFICATION
            ),
            ExecutionAttemptState.SUCCEEDED: (
                ExecutionAttemptRecovery.TERMINAL_SUCCESS
            ),
            ExecutionAttemptState.FAILED: (
                ExecutionAttemptRecovery.TERMINAL_FAILURE
            ),
            ExecutionAttemptState.ABANDONED: ExecutionAttemptRecovery.ABANDONED,
        }[self.state]

    def authority_dict(self) -> dict[str, object]:
        return {
            "attempt_id": self.attempt_id,
            "session_id": self.session_id,
            "principal": self.principal,
            "worker_id": self.worker_id,
            "plan_fingerprint": self.plan_fingerprint,
            "execution_seal_id": self.execution_seal_id,
            "execution_fence_digest": self.execution_fence_digest,
            "fencing_token": self.fencing_token,
            "runtime_trust_digest": self.runtime_trust_digest,
            "release_evidence_digest": self.release_evidence_digest,
            "execution_backend_id": self.execution_backend_id,
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
            "schema_version": self.schema_version,
            **self.authority_dict(),
            "authority_digest": self.authority_digest,
            "state": self.state.value,
            "recovery": self.recovery.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "terminal_evidence_digest": self.terminal_evidence_digest,
            "error_type": self.error_type,
        }


@dataclass(frozen=True)
class StoredExecutionAttempt:
    revision: int
    attempt: AIExecutionAttempt

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError("execution attempt revision must be positive")

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "attempt": self.attempt.to_dict(),
        }


@dataclass(frozen=True)
class ExecutionAttemptSessionHead:
    """Discoverable binding from one AI session to its execution attempt."""

    session_id: str
    attempt_id: str
    authority_digest: str

    def __post_init__(self) -> None:
        if not self.session_id or len(self.session_id) > 256:
            raise ValueError("invalid execution attempt session head session_id")
        if not self.attempt_id or len(self.attempt_id) > 256:
            raise ValueError("invalid execution attempt session head attempt_id")
        object.__setattr__(
            self,
            "authority_digest",
            _digest("authority_digest", self.authority_digest),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "attempt_id": self.attempt_id,
            "authority_digest": self.authority_digest,
        }


class ExecutionAttemptConflict(RuntimeError):
    pass


class AIExecutionAttemptStore:
    """CAS-backed execution-attempt evidence with strict state transitions."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = "shell-ai-execution-attempt",
        max_retries: int = 8,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid execution attempt namespace")
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or not 1 <= max_retries <= 64
        ):
            raise ValueError("execution attempt max_retries outside supported range")
        self.backend = backend
        self.namespace = namespace
        self.max_retries = max_retries
        self._clock = clock

    @staticmethod
    def key(attempt_id: str) -> str:
        if not attempt_id or len(attempt_id) > 256:
            raise ValueError("invalid execution attempt id")
        return "attempt:" + hashlib.sha256(attempt_id.encode()).hexdigest()

    @staticmethod
    def session_key(session_id: str) -> str:
        if not session_id or len(session_id) > 256:
            raise ValueError("invalid execution attempt session_id")
        return "session:" + hashlib.sha256(session_id.encode()).hexdigest()

    def _bind_session_head(
        self,
        attempt: AIExecutionAttempt,
    ) -> ExecutionAttemptSessionHead:
        head = ExecutionAttemptSessionHead(
            attempt.session_id,
            attempt.attempt_id,
            attempt.authority_digest,
        )
        key = self.session_key(attempt.session_id)
        try:
            self.backend.put_if_absent(
                self.namespace,
                key,
                head,
            )
            return head
        except DistributedStateConflict as exc:
            current = self.backend.get(self.namespace, key)
            if current is None:
                raise ExecutionAttemptConflict(
                    "execution attempt session-head race lost without winner"
                ) from exc
            if not isinstance(current.value, ExecutionAttemptSessionHead):
                raise RuntimeError(
                    "execution attempt session head type mismatch"
                ) from exc
            existing = current.value
            if (
                existing.attempt_id == attempt.attempt_id
                and existing.authority_digest == attempt.authority_digest
            ):
                return existing
            raise ExecutionAttemptConflict(
                "AI session already binds a different execution attempt"
            ) from exc

    def reserve(
        self,
        *,
        attempt_id: str,
        session_id: str,
        principal: str,
        worker_id: str,
        plan_fingerprint: str,
        execution_seal_id: str,
        execution_fence_digest: str = "",
        fencing_token: int | None = None,
        runtime_trust_digest: str = "",
        release_evidence_digest: str = "",
        execution_backend_id: str = "",
    ) -> StoredExecutionAttempt:
        now = self._clock()
        attempt = AIExecutionAttempt(
            1,
            attempt_id,
            session_id,
            principal,
            worker_id,
            plan_fingerprint,
            execution_seal_id,
            ExecutionAttemptState.AUTHORIZED,
            now,
            now,
            execution_fence_digest,
            fencing_token,
            runtime_trust_digest,
            release_evidence_digest,
            execution_backend_id,
        )
        key = self.key(attempt_id)
        try:
            record = self.backend.put_if_absent(
                self.namespace,
                key,
                attempt,
            )
            stored = StoredExecutionAttempt(record.revision, attempt)
        except DistributedStateConflict as exc:
            current = self.current(attempt_id)
            if current is not None and (
                current.attempt.authority_digest == attempt.authority_digest
            ):
                stored = current
            else:
                raise ExecutionAttemptConflict(
                    "execution attempt id already binds different authority"
                ) from exc

        try:
            self._bind_session_head(stored.attempt)
        except ExecutionAttemptConflict:
            # A competing attempt may have won the session pointer after this
            # immutable attempt record was created. It never crossed the
            # backend boundary, so make that orphan terminal when possible.
            try:
                current = self.current(attempt_id)
                if (
                    current is not None
                    and current.attempt.state
                    is ExecutionAttemptState.AUTHORIZED
                ):
                    self.abandon(current.attempt)
            except Exception:
                pass
            raise
        return stored

    def current(self, attempt_id: str) -> StoredExecutionAttempt | None:
        record = self.backend.get(self.namespace, self.key(attempt_id))
        if record is None:
            return None
        if not isinstance(record.value, AIExecutionAttempt):
            raise RuntimeError("execution attempt backend value type mismatch")
        return StoredExecutionAttempt(record.revision, record.value)

    def session_head(
        self,
        session_id: str,
    ) -> ExecutionAttemptSessionHead | None:
        record = self.backend.get(
            self.namespace,
            self.session_key(session_id),
        )
        if record is None:
            return None
        if not isinstance(record.value, ExecutionAttemptSessionHead):
            raise RuntimeError("execution attempt session head type mismatch")
        if record.value.session_id != session_id:
            raise RuntimeError("execution attempt session head identity mismatch")
        return record.value

    def current_for_session(
        self,
        session_id: str,
    ) -> StoredExecutionAttempt | None:
        head = self.session_head(session_id)
        if head is None:
            return None
        current = self.current(head.attempt_id)
        if current is None:
            raise ExecutionAttemptConflict(
                "execution attempt session head references missing attempt"
            )
        if current.attempt.session_id != session_id:
            raise ExecutionAttemptConflict(
                "execution attempt session head references wrong session"
            )
        if current.attempt.authority_digest != head.authority_digest:
            raise ExecutionAttemptConflict(
                "execution attempt session head authority mismatch"
            )
        return current

    @staticmethod
    def _same_authority(
        current: AIExecutionAttempt,
        supplied: AIExecutionAttempt,
    ) -> None:
        if current.attempt_id != supplied.attempt_id:
            raise ExecutionAttemptConflict("execution attempt identity mismatch")
        if current.authority_digest != supplied.authority_digest:
            raise ExecutionAttemptConflict(
                "execution attempt authority binding mismatch"
            )

    def _transition(
        self,
        supplied: AIExecutionAttempt,
        *,
        allowed_from: frozenset[ExecutionAttemptState],
        target: ExecutionAttemptState,
        terminal_evidence_digest: str = "",
        error_type: str = "",
    ) -> StoredExecutionAttempt:
        key = self.key(supplied.attempt_id)
        for _ in range(self.max_retries):
            record = self.backend.get(self.namespace, key)
            if record is None or not isinstance(record.value, AIExecutionAttempt):
                raise ExecutionAttemptConflict("execution attempt is missing")
            current = record.value
            self._same_authority(current, supplied)

            if current.state is target:
                if (
                    current.terminal_evidence_digest == terminal_evidence_digest
                    and current.error_type == error_type
                ):
                    return StoredExecutionAttempt(record.revision, current)
                raise ExecutionAttemptConflict(
                    "execution attempt terminal state differs"
                )
            if current.state not in allowed_from:
                raise ExecutionAttemptConflict(
                    f"execution attempt cannot move from {current.state.value} "
                    f"to {target.value}"
                )

            updated = replace(
                current,
                state=target,
                updated_at=self._clock(),
                terminal_evidence_digest=terminal_evidence_digest,
                error_type=error_type,
            )
            try:
                stored = self.backend.compare_and_swap(
                    self.namespace,
                    key,
                    expected_revision=record.revision,
                    value=updated,
                )
                return StoredExecutionAttempt(stored.revision, updated)
            except DistributedStateConflict:
                continue
        raise ExecutionAttemptConflict(
            "execution attempt transition CAS retry bound exceeded"
        )

    def enter_boundary(
        self,
        attempt: AIExecutionAttempt,
    ) -> StoredExecutionAttempt:
        return self._transition(
            attempt,
            allowed_from=frozenset({ExecutionAttemptState.AUTHORIZED}),
            target=ExecutionAttemptState.BOUNDARY_ENTERED,
        )

    def succeed(
        self,
        attempt: AIExecutionAttempt,
        *,
        terminal_evidence_digest: str,
    ) -> StoredExecutionAttempt:
        terminal_evidence_digest = _digest(
            "terminal_evidence_digest",
            terminal_evidence_digest,
        )
        return self._transition(
            attempt,
            allowed_from=frozenset(
                {ExecutionAttemptState.BOUNDARY_ENTERED}
            ),
            target=ExecutionAttemptState.SUCCEEDED,
            terminal_evidence_digest=terminal_evidence_digest,
        )

    def fail(
        self,
        attempt: AIExecutionAttempt,
        *,
        error_type: str,
        terminal_evidence_digest: str = "",
    ) -> StoredExecutionAttempt:
        if not error_type or len(error_type) > 256:
            raise ValueError("invalid execution attempt error_type")
        terminal_evidence_digest = _digest(
            "terminal_evidence_digest",
            terminal_evidence_digest,
            optional=True,
        )
        return self._transition(
            attempt,
            allowed_from=frozenset(
                {ExecutionAttemptState.BOUNDARY_ENTERED}
            ),
            target=ExecutionAttemptState.FAILED,
            terminal_evidence_digest=terminal_evidence_digest,
            error_type=error_type,
        )

    def abandon(
        self,
        attempt: AIExecutionAttempt,
    ) -> StoredExecutionAttempt:
        """Abandon only before boundary entry; ambiguous attempts cannot be erased."""

        return self._transition(
            attempt,
            allowed_from=frozenset({ExecutionAttemptState.AUTHORIZED}),
            target=ExecutionAttemptState.ABANDONED,
        )

    def require_recovery(
        self,
        attempt_id: str,
    ) -> ExecutionAttemptRecovery:
        current = self.current(attempt_id)
        if current is None:
            raise ExecutionAttemptConflict("execution attempt is missing")
        return current.attempt.recovery


class AttemptTrackingExecutionBackend:
    """Transparent backend wrapper recording the process-boundary transition.

    The wrapper keeps the delegate backend ID and exposes the delegate through
    assurance_backend so service assurance evaluates the real sandbox/host
    backend instead of this evidence adapter.
    """

    def __init__(
        self,
        store: AIExecutionAttemptStore,
        attempt: AIExecutionAttempt,
        delegate: AIPlanExecutionBackend,
    ) -> None:
        if not isinstance(store, AIExecutionAttemptStore):
            raise TypeError("store must be AIExecutionAttemptStore")
        if not isinstance(attempt, AIExecutionAttempt):
            raise TypeError("attempt must be AIExecutionAttempt")
        if not isinstance(delegate, AIPlanExecutionBackend):
            raise TypeError("delegate must satisfy AIPlanExecutionBackend")
        if attempt.state is not ExecutionAttemptState.AUTHORIZED:
            raise ValueError(
                "tracking backend requires an authorized execution attempt"
            )
        self.store = store
        self._attempt = attempt
        self.delegate = delegate
        self.boundary_entered = False

    @property
    def backend_id(self) -> str:
        return self.delegate.backend_id

    @property
    def assurance_backend(self) -> AIPlanExecutionBackend:
        return self.delegate

    @property
    def attempt(self) -> AIExecutionAttempt:
        return self._attempt

    @property
    def binding(self):
        return getattr(self.delegate, "binding", None)

    def execute_plan(
        self,
        plan: ExecutionPlan,
        *,
        context: ExecutionContext,
    ) -> PlanExecutionReport:
        if self.boundary_entered:
            raise ExecutionAttemptConflict(
                "tracking backend may cross the execution boundary only once"
            )
        stored = self.store.enter_boundary(self._attempt)
        self._attempt = stored.attempt
        self.boundary_entered = True
        return self.delegate.execute_plan(
            plan,
            context=context,
        )

    def receipt_root(self) -> str:
        return self.delegate.receipt_root()
