"""Tamper-evident execution audit and replay contracts for Jeeves.

The ordinary runtime trace is excellent for observability, but a security
boundary needs a narrower contract: each consequential execution transition must
be cryptographically chained to the previous transition and independently
replayable without trusting mutable in-memory objects.

This module provides that contract.  It intentionally uses only deterministic
host data and SHA-256 fingerprints.  A hash chain is tamper-*evident*, not a
signature; callers that need non-repudiation can persist the exported checkpoint
under an external signature or append-only store.

The protocol recognizes these phases for one guarded tool operation:

    intent_bound -> decision_made -> authorization_issued
      -> authorization_consumed -> tool_observed
      -> evidence_ingested -> transition_learned -> execution_finalized

Rejected/failed operations may terminate early through ``execution_denied`` or
``execution_failed``.  The replay verifier checks both cryptographic continuity
and protocol ordering so a syntactically valid hash chain cannot quietly omit or
reorder required security boundaries.
"""

from __future__ import annotations

import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

from .types import (
    AgentContractError,
    finite_number,
    json_safe,
    positive_int,
    require_id,
    stable_fingerprint,
    stable_id,
)


GENESIS_HASH = "0" * 64


class ExecutionAuditError(RuntimeError):
    """Raised when an audit ledger or replay contract is malformed."""


class AuditEventKind(str, Enum):
    INTENT_BOUND = "intent_bound"
    DECISION_MADE = "decision_made"
    EXECUTION_DENIED = "execution_denied"
    AUTHORIZATION_ISSUED = "authorization_issued"
    AUTHORIZATION_CONSUMED = "authorization_consumed"
    TOOL_OBSERVED = "tool_observed"
    EVIDENCE_INGESTED = "evidence_ingested"
    TRANSITION_LEARNED = "transition_learned"
    EXECUTION_FINALIZED = "execution_finalized"
    EXECUTION_FAILED = "execution_failed"
    CHECKPOINT_BOUND = "checkpoint_bound"
    RUN_RESUMED = "run_resumed"


class AuditSeverity(str, Enum):
    INFO = "info"
    SECURITY = "security"
    WARNING = "warning"
    ERROR = "error"


class ReplayIssueKind(str, Enum):
    EMPTY_LEDGER = "empty_ledger"
    RUN_MISMATCH = "run_mismatch"
    SEQUENCE_GAP = "sequence_gap"
    PREVIOUS_HASH_MISMATCH = "previous_hash_mismatch"
    EVENT_HASH_MISMATCH = "event_hash_mismatch"
    TIME_REGRESSION = "time_regression"
    DUPLICATE_EVENT_ID = "duplicate_event_id"
    OPERATION_REOPENED = "operation_reopened"
    PROTOCOL_ORDER = "protocol_order"
    REQUIRED_FIELD_MISSING = "required_field_missing"
    IDENTIFIER_MISMATCH = "identifier_mismatch"
    CHECKPOINT_MISMATCH = "checkpoint_mismatch"
    UNFINALIZED_OPERATION = "unfinalized_operation"


@dataclass(frozen=True, slots=True)
class ExecutionAuditEntry:
    event_id: str
    run_id: str
    operation_id: str | None
    sequence: int
    kind: AuditEventKind
    severity: AuditSeverity
    at: float
    previous_hash: str
    payload: Mapping[str, Any]
    event_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", require_id("event_id", self.event_id))
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        if self.operation_id is not None:
            object.__setattr__(
                self,
                "operation_id",
                require_id("operation_id", self.operation_id),
            )
        object.__setattr__(
            self,
            "sequence",
            positive_int("sequence", self.sequence, maximum=2_147_483_647),
        )
        if not isinstance(self.kind, AuditEventKind):
            object.__setattr__(self, "kind", AuditEventKind(str(self.kind)))
        if not isinstance(self.severity, AuditSeverity):
            object.__setattr__(self, "severity", AuditSeverity(str(self.severity)))
        at = finite_number("at", self.at)
        if at < 0:
            raise AgentContractError("audit timestamp must be non-negative")
        object.__setattr__(self, "at", at)
        previous = self._fingerprint("previous_hash", self.previous_hash)
        event_hash = self._fingerprint("event_hash", self.event_hash)
        object.__setattr__(self, "previous_hash", previous)
        object.__setattr__(self, "payload", json_safe(dict(self.payload)))
        object.__setattr__(self, "event_hash", event_hash)

    @staticmethod
    def _fingerprint(name: str, value: str) -> str:
        normalized = str(value).strip().lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise AgentContractError(f"{name} must be a sha256 hex fingerprint")
        return normalized

    @property
    def envelope(self) -> Mapping[str, Any]:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "operation_id": self.operation_id,
            "sequence": self.sequence,
            "kind": self.kind.value,
            "severity": self.severity.value,
            "at": self.at,
            "previous_hash": self.previous_hash,
            "payload": self.payload,
        }

    @property
    def expected_hash(self) -> str:
        return stable_fingerprint(self.envelope)

    @property
    def valid_hash(self) -> bool:
        return self.event_hash == self.expected_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            **dict(self.envelope),
            "event_hash": self.event_hash,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ExecutionAuditEntry":
        data = dict(raw)
        return cls(
            event_id=data["event_id"],
            run_id=data["run_id"],
            operation_id=data.get("operation_id"),
            sequence=data["sequence"],
            kind=AuditEventKind(data["kind"]),
            severity=AuditSeverity(data["severity"]),
            at=data["at"],
            previous_hash=data["previous_hash"],
            payload=data.get("payload", {}),
            event_hash=data["event_hash"],
        )


@dataclass(frozen=True, slots=True)
class ExecutionAuditCheckpoint:
    run_id: str
    event_count: int
    head_hash: str
    first_sequence: int
    last_sequence: int
    first_at: float | None
    last_at: float | None
    kind_counts: Mapping[str, int]
    checkpoint_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        if isinstance(self.event_count, bool) or not isinstance(self.event_count, int) or self.event_count < 0:
            raise AgentContractError("event_count must be a non-negative integer")
        if self.event_count == 0:
            if self.first_sequence != 0 or self.last_sequence != 0:
                raise AgentContractError("empty audit checkpoint must use zero sequence bounds")
        else:
            positive_int("first_sequence", self.first_sequence)
            positive_int("last_sequence", self.last_sequence)
            if self.first_sequence > self.last_sequence:
                raise AgentContractError("audit checkpoint sequence bounds are inverted")
        for name in ("head_hash", "checkpoint_fingerprint"):
            normalized = str(getattr(self, name)).strip().lower()
            if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
                raise AgentContractError(f"{name} must be sha256 hex")
            object.__setattr__(self, name, normalized)
        if self.first_at is not None:
            object.__setattr__(self, "first_at", finite_number("first_at", self.first_at))
        if self.last_at is not None:
            object.__setattr__(self, "last_at", finite_number("last_at", self.last_at))
        if self.first_at is not None and self.last_at is not None and self.last_at < self.first_at:
            raise AgentContractError("audit checkpoint time bounds are inverted")
        counts: dict[str, int] = {}
        for key, value in dict(self.kind_counts).items():
            key = str(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError("kind counts must be non-negative integers")
            counts[key] = value
        object.__setattr__(self, "kind_counts", dict(sorted(counts.items())))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "event_count": self.event_count,
            "head_hash": self.head_hash,
            "first_sequence": self.first_sequence,
            "last_sequence": self.last_sequence,
            "first_at": self.first_at,
            "last_at": self.last_at,
            "kind_counts": dict(self.kind_counts),
            "checkpoint_fingerprint": self.checkpoint_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class ReplayIssue:
    kind: ReplayIssueKind
    sequence: int | None
    operation_id: str | None
    message: str
    expected: Any = None
    actual: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ReplayIssueKind):
            object.__setattr__(self, "kind", ReplayIssueKind(str(self.kind)))
        if self.sequence is not None:
            positive_int("sequence", self.sequence)
        if self.operation_id is not None:
            object.__setattr__(self, "operation_id", require_id("operation_id", self.operation_id))
        if not isinstance(self.message, str) or not self.message.strip():
            raise AgentContractError("replay issue message must be non-empty")
        object.__setattr__(self, "message", self.message.strip()[:4096])
        object.__setattr__(self, "expected", json_safe(self.expected))
        object.__setattr__(self, "actual", json_safe(self.actual))


@dataclass(frozen=True, slots=True)
class OperationReplay:
    operation_id: str
    event_ids: tuple[str, ...]
    terminal_kind: AuditEventKind | None
    intent_fingerprint: str | None
    decision_id: str | None
    decision_fingerprint: str | None
    token_id: str | None
    permit_id: str | None
    call_id: str | None
    observation_fingerprint: str | None
    evidence_ids: tuple[str, ...]
    experience_id: str | None
    finalized: bool


@dataclass(frozen=True, slots=True)
class ReplayReport:
    run_id: str | None
    valid: bool
    entries_checked: int
    head_hash: str
    issues: tuple[ReplayIssue, ...]
    operations: tuple[OperationReplay, ...]
    checkpoint: ExecutionAuditCheckpoint | None
    fingerprint: str


class ExecutionAuditLedger:
    """Thread-safe append-only SHA-256 chain for one Jeeves run."""

    def __init__(
        self,
        run_id: str,
        *,
        clock: Callable[[], float] = time.time,
        maximum_events: int = 1_000_000,
    ) -> None:
        self.run_id = require_id("run_id", run_id)
        self._clock = clock
        self.maximum_events = positive_int("maximum_events", maximum_events, maximum=20_000_000)
        self._entries: list[ExecutionAuditEntry] = []
        self._lock = threading.RLock()

    def append(
        self,
        kind: AuditEventKind,
        payload: Mapping[str, Any],
        *,
        operation_id: str | None = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        at: float | None = None,
    ) -> ExecutionAuditEntry:
        if not isinstance(kind, AuditEventKind):
            kind = AuditEventKind(str(kind))
        if not isinstance(severity, AuditSeverity):
            severity = AuditSeverity(str(severity))
        if operation_id is not None:
            operation_id = require_id("operation_id", operation_id)
        clean_payload = json_safe(dict(payload))
        timestamp = self._clock() if at is None else at
        timestamp = finite_number("at", timestamp)
        if timestamp < 0:
            raise ExecutionAuditError("clock returned negative audit time")
        with self._lock:
            if len(self._entries) >= self.maximum_events:
                raise ExecutionAuditError("execution audit event capacity exhausted")
            sequence = len(self._entries) + 1
            previous_hash = self._entries[-1].event_hash if self._entries else GENESIS_HASH
            event_id = stable_id(
                "audit_event",
                {
                    "run": self.run_id,
                    "sequence": sequence,
                    "kind": kind.value,
                    "operation": operation_id,
                    "previous": previous_hash,
                    "payload": clean_payload,
                },
            )
            envelope = {
                "event_id": event_id,
                "run_id": self.run_id,
                "operation_id": operation_id,
                "sequence": sequence,
                "kind": kind.value,
                "severity": severity.value,
                "at": timestamp,
                "previous_hash": previous_hash,
                "payload": clean_payload,
            }
            event_hash = stable_fingerprint(envelope)
            entry = ExecutionAuditEntry(
                event_id=event_id,
                run_id=self.run_id,
                operation_id=operation_id,
                sequence=sequence,
                kind=kind,
                severity=severity,
                at=timestamp,
                previous_hash=previous_hash,
                payload=clean_payload,
                event_hash=event_hash,
            )
            self._entries.append(entry)
            return entry

    def entries(self) -> tuple[ExecutionAuditEntry, ...]:
        with self._lock:
            return tuple(self._entries)

    def operation_entries(self, operation_id: str) -> tuple[ExecutionAuditEntry, ...]:
        operation_id = require_id("operation_id", operation_id)
        with self._lock:
            return tuple(item for item in self._entries if item.operation_id == operation_id)

    @property
    def head_hash(self) -> str:
        with self._lock:
            return self._entries[-1].event_hash if self._entries else GENESIS_HASH

    @property
    def event_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def checkpoint(self) -> ExecutionAuditCheckpoint:
        with self._lock:
            entries = tuple(self._entries)
        counts = Counter(item.kind.value for item in entries)
        payload = {
            "run_id": self.run_id,
            "event_count": len(entries),
            "head_hash": entries[-1].event_hash if entries else GENESIS_HASH,
            "first_sequence": entries[0].sequence if entries else 0,
            "last_sequence": entries[-1].sequence if entries else 0,
            "first_at": entries[0].at if entries else None,
            "last_at": entries[-1].at if entries else None,
            "kind_counts": dict(sorted(counts.items())),
        }
        return ExecutionAuditCheckpoint(
            **payload,
            checkpoint_fingerprint=stable_fingerprint(payload),
        )

    def export(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(item.to_dict() for item in self.entries())

    @classmethod
    def restore(
        cls,
        run_id: str,
        records: Sequence[Mapping[str, Any]],
        *,
        clock: Callable[[], float] = time.time,
        maximum_events: int = 1_000_000,
        verify: bool = True,
    ) -> "ExecutionAuditLedger":
        ledger = cls(run_id, clock=clock, maximum_events=maximum_events)
        parsed = [ExecutionAuditEntry.from_dict(record) for record in records]
        with ledger._lock:
            ledger._entries = parsed
        if verify:
            report = ExecutionReplayVerifier().verify(parsed)
            if not report.valid:
                summary = "; ".join(issue.message for issue in report.issues[:5])
                raise ExecutionAuditError("cannot restore invalid audit chain: " + summary)
        return ledger


@dataclass(slots=True)
class _ReplayAccumulator:
    operation_id: str
    event_ids: list[str] = field(default_factory=list)
    last_stage: int = -1
    terminal_kind: AuditEventKind | None = None
    intent_fingerprint: str | None = None
    decision_id: str | None = None
    decision_fingerprint: str | None = None
    token_id: str | None = None
    permit_id: str | None = None
    call_id: str | None = None
    observation_fingerprint: str | None = None
    evidence_ids: tuple[str, ...] = ()
    experience_id: str | None = None
    finalized: bool = False


class ExecutionReplayVerifier:
    """Verify audit-chain integrity and guarded-execution protocol semantics."""

    _STAGE = {
        AuditEventKind.INTENT_BOUND: 0,
        AuditEventKind.DECISION_MADE: 1,
        AuditEventKind.AUTHORIZATION_ISSUED: 2,
        AuditEventKind.AUTHORIZATION_CONSUMED: 3,
        AuditEventKind.TOOL_OBSERVED: 4,
        AuditEventKind.EVIDENCE_INGESTED: 5,
        AuditEventKind.TRANSITION_LEARNED: 6,
        AuditEventKind.EXECUTION_FINALIZED: 7,
    }
    _TERMINAL = {
        AuditEventKind.EXECUTION_DENIED,
        AuditEventKind.EXECUTION_FAILED,
        AuditEventKind.EXECUTION_FINALIZED,
    }
    _REQUIRED_FIELDS = {
        AuditEventKind.INTENT_BOUND: ("intent_id", "intent_fingerprint", "call_id", "tool_name"),
        AuditEventKind.DECISION_MADE: ("decision_id", "decision_fingerprint", "disposition"),
        AuditEventKind.EXECUTION_DENIED: ("reason",),
        AuditEventKind.AUTHORIZATION_ISSUED: ("token_id", "authorization_fingerprint"),
        AuditEventKind.AUTHORIZATION_CONSUMED: ("permit_id", "authorization_fingerprint"),
        AuditEventKind.TOOL_OBSERVED: ("call_id", "observation_fingerprint", "ok"),
        AuditEventKind.EVIDENCE_INGESTED: ("evidence_ids", "evidence_fingerprint"),
        AuditEventKind.TRANSITION_LEARNED: ("experience_id", "model_fingerprint"),
        AuditEventKind.EXECUTION_FINALIZED: ("outcome", "verification_score"),
        AuditEventKind.EXECUTION_FAILED: ("reason",),
        AuditEventKind.CHECKPOINT_BOUND: ("checkpoint_sequence", "checkpoint_fingerprint"),
        AuditEventKind.RUN_RESUMED: ("checkpoint_sequence", "audit_head"),
    }

    def verify(
        self,
        entries: Sequence[ExecutionAuditEntry] | Iterable[ExecutionAuditEntry],
        *,
        expected_run_id: str | None = None,
        expected_checkpoint: ExecutionAuditCheckpoint | None = None,
        require_finalized_operations: bool = False,
    ) -> ReplayReport:
        items = tuple(entries)
        issues: list[ReplayIssue] = []
        if expected_run_id is not None:
            expected_run_id = require_id("expected_run_id", expected_run_id)
        if not items:
            if expected_checkpoint is not None and expected_checkpoint.event_count != 0:
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.CHECKPOINT_MISMATCH,
                        None,
                        None,
                        "expected non-empty checkpoint but audit ledger is empty",
                        expected_checkpoint.event_count,
                        0,
                    )
                )
            checkpoint = None
            fingerprint = stable_fingerprint({"run": expected_run_id, "issues": [issue.kind.value for issue in issues]})
            return ReplayReport(
                run_id=expected_run_id,
                valid=not issues,
                entries_checked=0,
                head_hash=GENESIS_HASH,
                issues=tuple(issues),
                operations=(),
                checkpoint=checkpoint,
                fingerprint=fingerprint,
            )

        run_id = items[0].run_id
        if expected_run_id is not None and run_id != expected_run_id:
            issues.append(
                ReplayIssue(
                    ReplayIssueKind.RUN_MISMATCH,
                    1,
                    items[0].operation_id,
                    "audit run id differs from expected run id",
                    expected_run_id,
                    run_id,
                )
            )
        seen_event_ids: set[str] = set()
        previous_hash = GENESIS_HASH
        previous_at = -1.0
        operations: dict[str, _ReplayAccumulator] = {}

        for index, entry in enumerate(items, start=1):
            if not isinstance(entry, ExecutionAuditEntry):
                raise TypeError("entries must contain ExecutionAuditEntry")
            if entry.run_id != run_id:
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.RUN_MISMATCH,
                        entry.sequence,
                        entry.operation_id,
                        "audit entry changes run id inside one chain",
                        run_id,
                        entry.run_id,
                    )
                )
            if entry.sequence != index:
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.SEQUENCE_GAP,
                        entry.sequence,
                        entry.operation_id,
                        "audit sequence is not contiguous and one-based",
                        index,
                        entry.sequence,
                    )
                )
            if entry.previous_hash != previous_hash:
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.PREVIOUS_HASH_MISMATCH,
                        entry.sequence,
                        entry.operation_id,
                        "audit previous_hash does not match preceding event",
                        previous_hash,
                        entry.previous_hash,
                    )
                )
            if not entry.valid_hash:
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.EVENT_HASH_MISMATCH,
                        entry.sequence,
                        entry.operation_id,
                        "audit event hash does not match canonical envelope",
                        entry.expected_hash,
                        entry.event_hash,
                    )
                )
            if entry.at + 1e-12 < previous_at:
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.TIME_REGRESSION,
                        entry.sequence,
                        entry.operation_id,
                        "audit wall-clock time moved backwards",
                        previous_at,
                        entry.at,
                    )
                )
            if entry.event_id in seen_event_ids:
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.DUPLICATE_EVENT_ID,
                        entry.sequence,
                        entry.operation_id,
                        "audit event id is duplicated",
                        None,
                        entry.event_id,
                    )
                )
            seen_event_ids.add(entry.event_id)
            previous_hash = entry.event_hash
            previous_at = max(previous_at, entry.at)
            self._validate_required_fields(entry, issues)
            if entry.operation_id is not None:
                self._advance_operation(entry, operations, issues)

        operation_replays = tuple(
            self._freeze_operation(acc)
            for _, acc in sorted(operations.items())
        )
        if require_finalized_operations:
            for operation in operation_replays:
                if not operation.finalized and operation.terminal_kind not in {
                    AuditEventKind.EXECUTION_DENIED,
                    AuditEventKind.EXECUTION_FAILED,
                }:
                    issues.append(
                        ReplayIssue(
                            ReplayIssueKind.UNFINALIZED_OPERATION,
                            None,
                            operation.operation_id,
                            "guarded operation has no terminal audit event",
                        )
                    )

        checkpoint = self._checkpoint_from_entries(run_id, items)
        if expected_checkpoint is not None:
            self._compare_checkpoint(expected_checkpoint, checkpoint, issues)
        fingerprint = stable_fingerprint(
            {
                "run_id": run_id,
                "entries": len(items),
                "head": previous_hash,
                "issues": [
                    (
                        issue.kind.value,
                        issue.sequence,
                        issue.operation_id,
                        issue.message,
                        issue.expected,
                        issue.actual,
                    )
                    for issue in issues
                ],
                "operations": [
                    (
                        operation.operation_id,
                        operation.terminal_kind.value if operation.terminal_kind else None,
                        operation.event_ids,
                        operation.finalized,
                    )
                    for operation in operation_replays
                ],
            }
        )
        return ReplayReport(
            run_id=run_id,
            valid=not issues,
            entries_checked=len(items),
            head_hash=previous_hash,
            issues=tuple(issues),
            operations=operation_replays,
            checkpoint=checkpoint,
            fingerprint=fingerprint,
        )

    def _validate_required_fields(
        self,
        entry: ExecutionAuditEntry,
        issues: list[ReplayIssue],
    ) -> None:
        required = self._REQUIRED_FIELDS.get(entry.kind, ())
        for field_name in required:
            if field_name not in entry.payload:
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.REQUIRED_FIELD_MISSING,
                        entry.sequence,
                        entry.operation_id,
                        f"{entry.kind.value} payload is missing {field_name}",
                    )
                )

    def _advance_operation(
        self,
        entry: ExecutionAuditEntry,
        operations: dict[str, _ReplayAccumulator],
        issues: list[ReplayIssue],
    ) -> None:
        assert entry.operation_id is not None
        acc = operations.setdefault(entry.operation_id, _ReplayAccumulator(entry.operation_id))
        if acc.terminal_kind is not None:
            issues.append(
                ReplayIssue(
                    ReplayIssueKind.OPERATION_REOPENED,
                    entry.sequence,
                    entry.operation_id,
                    "audit event appears after operation terminal state",
                    acc.terminal_kind.value,
                    entry.kind.value,
                )
            )
        stage = self._STAGE.get(entry.kind)
        if stage is not None:
            if stage < acc.last_stage:
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.PROTOCOL_ORDER,
                        entry.sequence,
                        entry.operation_id,
                        "guarded execution protocol moved backwards",
                        acc.last_stage,
                        stage,
                    )
                )
            if stage > acc.last_stage + 1 and acc.last_stage >= 0:
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.PROTOCOL_ORDER,
                        entry.sequence,
                        entry.operation_id,
                        "guarded execution protocol skipped a required stage",
                        acc.last_stage + 1,
                        stage,
                    )
                )
            if acc.last_stage < 0 and stage != 0:
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.PROTOCOL_ORDER,
                        entry.sequence,
                        entry.operation_id,
                        "guarded operation did not start with intent binding",
                        0,
                        stage,
                    )
                )
            acc.last_stage = max(acc.last_stage, stage)
        acc.event_ids.append(entry.event_id)
        if entry.kind in self._TERMINAL:
            acc.terminal_kind = entry.kind
        payload = entry.payload
        if entry.kind is AuditEventKind.INTENT_BOUND:
            acc.intent_fingerprint = self._optional_text(payload.get("intent_fingerprint"))
            acc.call_id = self._optional_text(payload.get("call_id"))
        elif entry.kind is AuditEventKind.DECISION_MADE:
            acc.decision_id = self._optional_text(payload.get("decision_id"))
            acc.decision_fingerprint = self._optional_text(payload.get("decision_fingerprint"))
        elif entry.kind is AuditEventKind.AUTHORIZATION_ISSUED:
            acc.token_id = self._optional_text(payload.get("token_id"))
            self._assert_same("decision_id", acc.decision_id, payload.get("decision_id"), entry, issues)
        elif entry.kind is AuditEventKind.AUTHORIZATION_CONSUMED:
            acc.permit_id = self._optional_text(payload.get("permit_id"))
            self._assert_same("token_id", acc.token_id, payload.get("token_id"), entry, issues)
        elif entry.kind is AuditEventKind.TOOL_OBSERVED:
            self._assert_same("call_id", acc.call_id, payload.get("call_id"), entry, issues)
            acc.observation_fingerprint = self._optional_text(payload.get("observation_fingerprint"))
        elif entry.kind is AuditEventKind.EVIDENCE_INGESTED:
            raw_ids = payload.get("evidence_ids", [])
            if isinstance(raw_ids, list) and all(isinstance(item, str) for item in raw_ids):
                acc.evidence_ids = tuple(raw_ids)
        elif entry.kind is AuditEventKind.TRANSITION_LEARNED:
            acc.experience_id = self._optional_text(payload.get("experience_id"))
        elif entry.kind is AuditEventKind.EXECUTION_FINALIZED:
            acc.finalized = True

    def _assert_same(
        self,
        field_name: str,
        expected: str | None,
        actual: Any,
        entry: ExecutionAuditEntry,
        issues: list[ReplayIssue],
    ) -> None:
        if expected is None or actual is None:
            return
        actual_text = str(actual)
        if expected != actual_text:
            issues.append(
                ReplayIssue(
                    ReplayIssueKind.IDENTIFIER_MISMATCH,
                    entry.sequence,
                    entry.operation_id,
                    f"{field_name} changed within guarded operation",
                    expected,
                    actual_text,
                )
            )

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _freeze_operation(acc: _ReplayAccumulator) -> OperationReplay:
        return OperationReplay(
            operation_id=acc.operation_id,
            event_ids=tuple(acc.event_ids),
            terminal_kind=acc.terminal_kind,
            intent_fingerprint=acc.intent_fingerprint,
            decision_id=acc.decision_id,
            decision_fingerprint=acc.decision_fingerprint,
            token_id=acc.token_id,
            permit_id=acc.permit_id,
            call_id=acc.call_id,
            observation_fingerprint=acc.observation_fingerprint,
            evidence_ids=acc.evidence_ids,
            experience_id=acc.experience_id,
            finalized=acc.finalized,
        )

    @staticmethod
    def _checkpoint_from_entries(
        run_id: str,
        items: Sequence[ExecutionAuditEntry],
    ) -> ExecutionAuditCheckpoint:
        counts = Counter(item.kind.value for item in items)
        payload = {
            "run_id": run_id,
            "event_count": len(items),
            "head_hash": items[-1].event_hash if items else GENESIS_HASH,
            "first_sequence": items[0].sequence if items else 0,
            "last_sequence": items[-1].sequence if items else 0,
            "first_at": items[0].at if items else None,
            "last_at": items[-1].at if items else None,
            "kind_counts": dict(sorted(counts.items())),
        }
        return ExecutionAuditCheckpoint(
            **payload,
            checkpoint_fingerprint=stable_fingerprint(payload),
        )

    @staticmethod
    def _compare_checkpoint(
        expected: ExecutionAuditCheckpoint,
        actual: ExecutionAuditCheckpoint,
        issues: list[ReplayIssue],
    ) -> None:
        fields = (
            "run_id",
            "event_count",
            "head_hash",
            "first_sequence",
            "last_sequence",
            "kind_counts",
            "checkpoint_fingerprint",
        )
        for field_name in fields:
            expected_value = getattr(expected, field_name)
            actual_value = getattr(actual, field_name)
            if expected_value != actual_value:
                issues.append(
                    ReplayIssue(
                        ReplayIssueKind.CHECKPOINT_MISMATCH,
                        None,
                        None,
                        f"audit checkpoint field {field_name} differs",
                        expected_value,
                        actual_value,
                    )
                )


class InMemoryExecutionAuditStore:
    """Bounded in-memory audit-ledger registry shared across runtime resumes."""

    def __init__(
        self,
        *,
        maximum_runs: int = 10_000,
        maximum_events_per_run: int = 1_000_000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.maximum_runs = positive_int("maximum_runs", maximum_runs, maximum=1_000_000)
        self.maximum_events_per_run = positive_int(
            "maximum_events_per_run",
            maximum_events_per_run,
            maximum=20_000_000,
        )
        self._clock = clock
        self._ledgers: dict[str, ExecutionAuditLedger] = {}
        self._order: list[str] = []
        self._lock = threading.RLock()

    def get_or_create(self, run_id: str) -> ExecutionAuditLedger:
        run_id = require_id("run_id", run_id)
        with self._lock:
            ledger = self._ledgers.get(run_id)
            if ledger is not None:
                return ledger
            if len(self._ledgers) >= self.maximum_runs:
                self._evict_oldest_empty_or_oldest()
            ledger = ExecutionAuditLedger(
                run_id,
                clock=self._clock,
                maximum_events=self.maximum_events_per_run,
            )
            self._ledgers[run_id] = ledger
            self._order.append(run_id)
            return ledger

    def get(self, run_id: str) -> ExecutionAuditLedger | None:
        run_id = require_id("run_id", run_id)
        with self._lock:
            return self._ledgers.get(run_id)

    def remove(self, run_id: str) -> bool:
        run_id = require_id("run_id", run_id)
        with self._lock:
            removed = self._ledgers.pop(run_id, None) is not None
            if removed:
                self._order = [item for item in self._order if item != run_id]
            return removed

    def runs(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._order)

    def verify(
        self,
        run_id: str,
        *,
        expected_checkpoint: ExecutionAuditCheckpoint | None = None,
        require_finalized_operations: bool = False,
    ) -> ReplayReport:
        ledger = self.get(run_id)
        if ledger is None:
            return ExecutionReplayVerifier().verify(
                (),
                expected_run_id=run_id,
                expected_checkpoint=expected_checkpoint,
                require_finalized_operations=require_finalized_operations,
            )
        return ExecutionReplayVerifier().verify(
            ledger.entries(),
            expected_run_id=run_id,
            expected_checkpoint=expected_checkpoint,
            require_finalized_operations=require_finalized_operations,
        )

    def _evict_oldest_empty_or_oldest(self) -> None:
        for run_id in tuple(self._order):
            ledger = self._ledgers.get(run_id)
            if ledger is not None and ledger.event_count == 0:
                self._ledgers.pop(run_id, None)
                self._order.remove(run_id)
                return
        if self._order:
            oldest = self._order.pop(0)
            self._ledgers.pop(oldest, None)