"""Durable, replayable AI-chat turn runtime contracts.

This module is deliberately provider-neutral and side-effect aware. It models
one assistant turn as an append-only transition journal whose events are
digest-chained. The runtime does not execute models or tools; it defines the
state, budget, replay, and recovery invariants that those execution planes must
obey.

Key invariants:
- streamed UI output is never authoritative completion state;
- terminal states cannot transition;
- event sequence and previous-event digests are monotonic and exact;
- consequential tool ambiguity is reconciled before retry;
- resource budgets are hard bounds and child budgets cannot amplify authority;
- recovery decisions are deterministic from durable snapshot state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Iterable, Mapping

from .contracts import SideEffectClass, digest_json


CHAT_TURN_SCHEMA_VERSION = 1


class TurnRuntimeError(ValueError):
    """A durable turn invariant was violated."""


class TurnState(str, Enum):
    RECEIVED = "received"
    ADMITTED = "admitted"
    USER_MESSAGE_COMMITTED = "user_message_committed"
    CONTEXT_COMPILING = "context_compiling"
    ROUTING = "routing"
    MODEL_RUNNING = "model_running"
    TOOL_REQUIRED = "tool_required"
    AWAITING_USER = "awaiting_user"
    TOOL_EXECUTING = "tool_executing"
    VERIFYING = "verifying"
    FINALIZING = "finalizing"
    ASSISTANT_MESSAGE_COMMITTED = "assistant_message_committed"
    MEMORY_PROPOSAL = "memory_proposal"
    COMPLETE = "complete"
    DEGRADED = "degraded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_TERMINAL = "failed_terminal"
    CANCELLED = "cancelled"
    QUARANTINED = "quarantined"


TERMINAL_STATES = frozenset(
    {
        TurnState.COMPLETE,
        TurnState.DEGRADED,
        TurnState.FAILED_RETRYABLE,
        TurnState.FAILED_TERMINAL,
        TurnState.CANCELLED,
        TurnState.QUARANTINED,
    }
)


class RecoveryAction(str, Enum):
    RESUME_ADMISSION = "resume_admission"
    RESUME_MESSAGE_COMMIT = "resume_message_commit"
    RESUME_CONTEXT = "resume_context"
    RESUME_ROUTING = "resume_routing"
    RETRY_MODEL = "retry_model"
    RESUME_TOOL_ADMISSION = "resume_tool_admission"
    RETRY_TOOL = "retry_tool"
    RECONCILE_TOOL = "reconcile_tool"
    WAIT_FOR_USER = "wait_for_user"
    RESUME_VERIFICATION = "resume_verification"
    RESUME_FINALIZATION = "resume_finalization"
    RESUME_MEMORY = "resume_memory"
    FINALIZE_COMPLETE = "finalize_complete"
    NOOP_TERMINAL = "noop_terminal"


class FailureClass(str, Enum):
    RETRYABLE = "retryable"
    TERMINAL = "terminal"
    POLICY = "policy"
    AMBIGUOUS_EXTERNAL_EFFECT = "ambiguous_external_effect"
    QUARANTINE = "quarantine"
    CANCELLED = "cancelled"


_CONSEQUENTIAL_EFFECTS = frozenset(
    {
        SideEffectClass.REVERSIBLE_WRITE,
        SideEffectClass.EXTERNAL_WRITE,
        SideEffectClass.SECURITY_SENSITIVE,
    }
)


_ALLOWED_TRANSITIONS: Mapping[TurnState, frozenset[TurnState]] = {
    TurnState.RECEIVED: frozenset(
        {TurnState.ADMITTED, TurnState.FAILED_TERMINAL, TurnState.CANCELLED}
    ),
    TurnState.ADMITTED: frozenset(
        {
            TurnState.USER_MESSAGE_COMMITTED,
            TurnState.FAILED_TERMINAL,
            TurnState.CANCELLED,
        }
    ),
    TurnState.USER_MESSAGE_COMMITTED: frozenset(
        {
            TurnState.CONTEXT_COMPILING,
            TurnState.FAILED_RETRYABLE,
            TurnState.FAILED_TERMINAL,
            TurnState.CANCELLED,
        }
    ),
    TurnState.CONTEXT_COMPILING: frozenset(
        {
            TurnState.ROUTING,
            TurnState.FAILED_RETRYABLE,
            TurnState.FAILED_TERMINAL,
            TurnState.CANCELLED,
        }
    ),
    TurnState.ROUTING: frozenset(
        {
            TurnState.MODEL_RUNNING,
            TurnState.AWAITING_USER,
            TurnState.FAILED_RETRYABLE,
            TurnState.FAILED_TERMINAL,
            TurnState.CANCELLED,
        }
    ),
    TurnState.MODEL_RUNNING: frozenset(
        {
            TurnState.TOOL_REQUIRED,
            TurnState.VERIFYING,
            TurnState.AWAITING_USER,
            TurnState.FAILED_RETRYABLE,
            TurnState.FAILED_TERMINAL,
            TurnState.CANCELLED,
            TurnState.DEGRADED,
            TurnState.QUARANTINED,
        }
    ),
    TurnState.TOOL_REQUIRED: frozenset(
        {
            TurnState.TOOL_EXECUTING,
            TurnState.AWAITING_USER,
            TurnState.MODEL_RUNNING,
            TurnState.FAILED_RETRYABLE,
            TurnState.FAILED_TERMINAL,
            TurnState.CANCELLED,
            TurnState.QUARANTINED,
        }
    ),
    TurnState.AWAITING_USER: frozenset(
        {
            TurnState.MODEL_RUNNING,
            TurnState.TOOL_EXECUTING,
            TurnState.FAILED_TERMINAL,
            TurnState.CANCELLED,
        }
    ),
    TurnState.TOOL_EXECUTING: frozenset(
        {
            TurnState.TOOL_REQUIRED,
            TurnState.MODEL_RUNNING,
            TurnState.VERIFYING,
            TurnState.FAILED_RETRYABLE,
            TurnState.FAILED_TERMINAL,
            TurnState.DEGRADED,
            TurnState.CANCELLED,
            TurnState.QUARANTINED,
        }
    ),
    TurnState.VERIFYING: frozenset(
        {
            TurnState.FINALIZING,
            TurnState.MODEL_RUNNING,
            TurnState.FAILED_RETRYABLE,
            TurnState.FAILED_TERMINAL,
            TurnState.DEGRADED,
            TurnState.QUARANTINED,
        }
    ),
    TurnState.FINALIZING: frozenset(
        {
            TurnState.ASSISTANT_MESSAGE_COMMITTED,
            TurnState.FAILED_RETRYABLE,
            TurnState.FAILED_TERMINAL,
            TurnState.QUARANTINED,
        }
    ),
    TurnState.ASSISTANT_MESSAGE_COMMITTED: frozenset(
        {TurnState.MEMORY_PROPOSAL, TurnState.COMPLETE, TurnState.DEGRADED}
    ),
    TurnState.MEMORY_PROPOSAL: frozenset(
        {TurnState.COMPLETE, TurnState.DEGRADED}
    ),
}


def _text(value: object, field_name: str, *, maximum: int = 1024) -> str:
    if not isinstance(value, str):
        raise TurnRuntimeError(f"{field_name} must be text")
    normalized = value.strip()
    if not normalized:
        raise TurnRuntimeError(f"{field_name} is empty")
    if len(normalized) > maximum:
        raise TurnRuntimeError(f"{field_name} exceeds maximum length")
    return normalized


def _optional_text(
    value: object | None,
    field_name: str,
    *,
    maximum: int = 2048,
) -> str | None:
    if value is None:
        return None
    return _text(value, field_name, maximum=maximum)


def _sha256(value: object, field_name: str) -> str:
    text = _text(value, field_name, maximum=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise TurnRuntimeError(f"{field_name} must be lowercase sha256")
    return text


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TurnRuntimeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise TurnRuntimeError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _nonnegative_int(value: object, field_name: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TurnRuntimeError(f"{field_name} must be integer")
    if not 0 <= value <= maximum:
        raise TurnRuntimeError(f"{field_name} outside hard bounds")
    return value


def _nonnegative_float(value: object, field_name: str, *, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TurnRuntimeError(f"{field_name} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= maximum:
        raise TurnRuntimeError(f"{field_name} outside hard bounds")
    return normalized


@dataclass(frozen=True, slots=True)
class ExecutionBudget:
    """Hard per-turn limits inherited by all child work."""

    max_wall_seconds: float = 120.0
    max_input_tokens: int = 200_000
    max_output_tokens: int = 32_000
    max_model_calls: int = 8
    max_tool_calls: int = 32
    max_agent_depth: int = 4
    max_parallel_workers: int = 8
    max_retrieval_queries: int = 16
    max_external_writes: int = 4
    max_cost_usd: float = 10.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_wall_seconds",
            _nonnegative_float(
                self.max_wall_seconds,
                "max_wall_seconds",
                maximum=86_400.0,
            ),
        )
        for name, maximum in (
            ("max_input_tokens", 10_000_000),
            ("max_output_tokens", 1_000_000),
            ("max_model_calls", 256),
            ("max_tool_calls", 4096),
            ("max_agent_depth", 32),
            ("max_parallel_workers", 512),
            ("max_retrieval_queries", 4096),
            ("max_external_writes", 1024),
        ):
            object.__setattr__(
                self,
                name,
                _nonnegative_int(getattr(self, name), name, maximum=maximum),
            )
        object.__setattr__(
            self,
            "max_cost_usd",
            _nonnegative_float(self.max_cost_usd, "max_cost_usd", maximum=1_000_000.0),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "max_wall_seconds": self.max_wall_seconds,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_model_calls": self.max_model_calls,
            "max_tool_calls": self.max_tool_calls,
            "max_agent_depth": self.max_agent_depth,
            "max_parallel_workers": self.max_parallel_workers,
            "max_retrieval_queries": self.max_retrieval_queries,
            "max_external_writes": self.max_external_writes,
            "max_cost_usd": self.max_cost_usd,
        }


@dataclass(frozen=True, slots=True)
class BudgetUsage:
    wall_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    agent_depth: int = 0
    parallel_workers: int = 0
    retrieval_queries: int = 0
    external_writes: int = 0
    cost_usd: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "wall_seconds",
            _nonnegative_float(self.wall_seconds, "wall_seconds", maximum=86_400.0),
        )
        for name, maximum in (
            ("input_tokens", 10_000_000),
            ("output_tokens", 1_000_000),
            ("model_calls", 256),
            ("tool_calls", 4096),
            ("agent_depth", 32),
            ("parallel_workers", 512),
            ("retrieval_queries", 4096),
            ("external_writes", 1024),
        ):
            object.__setattr__(
                self,
                name,
                _nonnegative_int(getattr(self, name), name, maximum=maximum),
            )
        object.__setattr__(
            self,
            "cost_usd",
            _nonnegative_float(self.cost_usd, "cost_usd", maximum=1_000_000.0),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "wall_seconds": self.wall_seconds,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "agent_depth": self.agent_depth,
            "parallel_workers": self.parallel_workers,
            "retrieval_queries": self.retrieval_queries,
            "external_writes": self.external_writes,
            "cost_usd": self.cost_usd,
        }

    def add(self, **delta: object) -> "BudgetUsage":
        allowed = set(self.as_dict())
        unknown = set(delta) - allowed
        if unknown:
            raise TurnRuntimeError(
                "unknown usage dimensions: " + ", ".join(sorted(unknown))
            )
        values = self.as_dict()
        for key, increment in delta.items():
            current = values[key]
            if isinstance(current, float):
                if isinstance(increment, bool) or not isinstance(increment, (int, float)):
                    raise TurnRuntimeError(f"{key} increment must be numeric")
                amount = float(increment)
            else:
                if isinstance(increment, bool) or not isinstance(increment, int):
                    raise TurnRuntimeError(f"{key} increment must be integer")
                amount = increment
            if amount < 0:
                raise TurnRuntimeError("usage increments cannot be negative")
            values[key] = current + amount
        return BudgetUsage(**values)


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    allowed: bool
    exceeded: tuple[str, ...]
    remaining: Mapping[str, float | int]


class BudgetGovernor:
    @staticmethod
    def assess(budget: ExecutionBudget, usage: BudgetUsage) -> BudgetDecision:
        pairs = {
            "wall_seconds": (usage.wall_seconds, budget.max_wall_seconds),
            "input_tokens": (usage.input_tokens, budget.max_input_tokens),
            "output_tokens": (usage.output_tokens, budget.max_output_tokens),
            "model_calls": (usage.model_calls, budget.max_model_calls),
            "tool_calls": (usage.tool_calls, budget.max_tool_calls),
            "agent_depth": (usage.agent_depth, budget.max_agent_depth),
            "parallel_workers": (
                usage.parallel_workers,
                budget.max_parallel_workers,
            ),
            "retrieval_queries": (
                usage.retrieval_queries,
                budget.max_retrieval_queries,
            ),
            "external_writes": (
                usage.external_writes,
                budget.max_external_writes,
            ),
            "cost_usd": (usage.cost_usd, budget.max_cost_usd),
        }
        exceeded = tuple(name for name, (used, limit) in pairs.items() if used > limit)
        remaining = {
            name: max(0, limit - used) for name, (used, limit) in pairs.items()
        }
        return BudgetDecision(
            allowed=not exceeded,
            exceeded=exceeded,
            remaining=remaining,
        )

    @staticmethod
    def require_within(budget: ExecutionBudget, usage: BudgetUsage) -> None:
        decision = BudgetGovernor.assess(budget, usage)
        if not decision.allowed:
            raise TurnRuntimeError(
                "turn budget exceeded: " + ", ".join(decision.exceeded)
            )

    @staticmethod
    def child_budget(
        parent: ExecutionBudget,
        parent_usage: BudgetUsage,
        requested: ExecutionBudget,
    ) -> ExecutionBudget:
        BudgetGovernor.require_within(parent, parent_usage)
        remaining = BudgetGovernor.assess(parent, parent_usage).remaining
        requested_map = requested.as_dict()
        mapping = {
            "max_wall_seconds": "wall_seconds",
            "max_input_tokens": "input_tokens",
            "max_output_tokens": "output_tokens",
            "max_model_calls": "model_calls",
            "max_tool_calls": "tool_calls",
            "max_agent_depth": "agent_depth",
            "max_parallel_workers": "parallel_workers",
            "max_retrieval_queries": "retrieval_queries",
            "max_external_writes": "external_writes",
            "max_cost_usd": "cost_usd",
        }
        violations = [
            budget_field
            for budget_field, usage_field in mapping.items()
            if requested_map[budget_field] > remaining[usage_field]
        ]
        if violations:
            raise TurnRuntimeError(
                "child budget amplifies remaining authority: "
                + ", ".join(sorted(violations))
            )
        return requested


@dataclass(frozen=True, slots=True)
class TurnEvent:
    """One immutable transition in an operation journal."""

    operation_id: str
    request_digest: str
    sequence: int
    from_state: TurnState
    to_state: TurnState
    observed_at: datetime
    previous_event_digest: str | None = None
    reason_code: str = "advance"
    failure_class: FailureClass | None = None
    tool_call_id: str | None = None
    tool_side_effect: SideEffectClass | None = None
    tool_receipt_ref: str | None = None
    tool_reconciliation_ref: str | None = None
    external_effect_started: bool = False
    provider_receipt_ref: str | None = None
    usage: BudgetUsage | None = None
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "operation_id", _text(self.operation_id, "operation_id", maximum=256)
        )
        object.__setattr__(
            self, "request_digest", _sha256(self.request_digest, "request_digest")
        )
        object.__setattr__(
            self,
            "sequence",
            _nonnegative_int(self.sequence, "sequence", maximum=10_000_000),
        )
        if self.sequence < 1:
            raise TurnRuntimeError("event sequence must start at one")
        if not isinstance(self.from_state, TurnState):
            object.__setattr__(self, "from_state", TurnState(str(self.from_state)))
        if not isinstance(self.to_state, TurnState):
            object.__setattr__(self, "to_state", TurnState(str(self.to_state)))
        object.__setattr__(
            self, "observed_at", _utc(self.observed_at, "observed_at")
        )
        if self.previous_event_digest is not None:
            object.__setattr__(
                self,
                "previous_event_digest",
                _sha256(self.previous_event_digest, "previous_event_digest"),
            )
        object.__setattr__(
            self, "reason_code", _text(self.reason_code, "reason_code", maximum=128)
        )
        if self.failure_class is not None and not isinstance(
            self.failure_class, FailureClass
        ):
            object.__setattr__(
                self, "failure_class", FailureClass(str(self.failure_class))
            )
        object.__setattr__(
            self,
            "tool_call_id",
            _optional_text(self.tool_call_id, "tool_call_id", maximum=512),
        )
        if self.tool_side_effect is not None and not isinstance(
            self.tool_side_effect, SideEffectClass
        ):
            object.__setattr__(
                self,
                "tool_side_effect",
                SideEffectClass(str(self.tool_side_effect)),
            )
        object.__setattr__(
            self,
            "tool_receipt_ref",
            _optional_text(
                self.tool_receipt_ref,
                "tool_receipt_ref",
                maximum=2048,
            ),
        )
        object.__setattr__(
            self,
            "tool_reconciliation_ref",
            _optional_text(
                self.tool_reconciliation_ref,
                "tool_reconciliation_ref",
                maximum=2048,
            ),
        )
        object.__setattr__(
            self,
            "provider_receipt_ref",
            _optional_text(
                self.provider_receipt_ref,
                "provider_receipt_ref",
                maximum=2048,
            ),
        )
        if self.usage is not None and not isinstance(self.usage, BudgetUsage):
            raise TurnRuntimeError("usage must be BudgetUsage")
        payload = dict(self.payload)
        digest_json(payload)
        object.__setattr__(self, "payload", payload)

        allowed = _ALLOWED_TRANSITIONS.get(self.from_state, frozenset())
        if self.to_state not in allowed:
            raise TurnRuntimeError(
                f"illegal turn transition: {self.from_state.value} -> "
                f"{self.to_state.value}"
            )
        if self.from_state in TERMINAL_STATES:
            raise TurnRuntimeError("terminal turn states cannot transition")
        if self.to_state is TurnState.TOOL_EXECUTING:
            if self.tool_call_id is None or self.tool_side_effect is None:
                raise TurnRuntimeError(
                    "tool execution transition requires call id and side-effect class"
                )
        if (
            self.to_state is TurnState.FAILED_RETRYABLE
            and self.failure_class
            in {FailureClass.TERMINAL, FailureClass.POLICY, FailureClass.QUARANTINE}
        ):
            raise TurnRuntimeError(
                "retryable state cannot carry terminal failure classification"
            )
        if self.to_state is TurnState.QUARANTINED and self.failure_class not in {
            FailureClass.QUARANTINE,
            FailureClass.POLICY,
        }:
            raise TurnRuntimeError(
                "quarantine transition requires quarantine or policy failure"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": CHAT_TURN_SCHEMA_VERSION,
            "operation_id": self.operation_id,
            "request_digest": self.request_digest,
            "sequence": self.sequence,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "observed_at": self.observed_at.isoformat(),
            "previous_event_digest": self.previous_event_digest,
            "reason_code": self.reason_code,
            "failure_class": (
                None if self.failure_class is None else self.failure_class.value
            ),
            "tool_call_id": self.tool_call_id,
            "tool_side_effect": (
                None if self.tool_side_effect is None else self.tool_side_effect.value
            ),
            "tool_receipt_ref": self.tool_receipt_ref,
            "tool_reconciliation_ref": self.tool_reconciliation_ref,
            "external_effect_started": self.external_effect_started,
            "provider_receipt_ref": self.provider_receipt_ref,
            "usage": None if self.usage is None else self.usage.as_dict(),
            "payload": dict(self.payload),
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())


@dataclass(frozen=True, slots=True)
class TurnSnapshot:
    """Replay-derived durable state for one AI-chat operation."""

    operation_id: str
    request_digest: str
    thread_id: str
    causal_user_message_id: str
    state: TurnState
    budget: ExecutionBudget
    usage: BudgetUsage = field(default_factory=BudgetUsage)
    next_sequence: int = 1
    last_event_digest: str | None = None
    pending_tool_call_id: str | None = None
    pending_tool_side_effect: SideEffectClass | None = None
    pending_tool_receipt_ref: str | None = None
    external_effect_started: bool = False
    provider_receipt_ref: str | None = None
    failure_class: FailureClass | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "operation_id", _text(self.operation_id, "operation_id", maximum=256)
        )
        object.__setattr__(
            self, "request_digest", _sha256(self.request_digest, "request_digest")
        )
        object.__setattr__(
            self, "thread_id", _text(self.thread_id, "thread_id", maximum=256)
        )
        object.__setattr__(
            self,
            "causal_user_message_id",
            _text(
                self.causal_user_message_id,
                "causal_user_message_id",
                maximum=256,
            ),
        )
        if not isinstance(self.state, TurnState):
            object.__setattr__(self, "state", TurnState(str(self.state)))
        if not isinstance(self.budget, ExecutionBudget):
            raise TurnRuntimeError("budget must be ExecutionBudget")
        if not isinstance(self.usage, BudgetUsage):
            raise TurnRuntimeError("usage must be BudgetUsage")
        object.__setattr__(
            self,
            "next_sequence",
            _nonnegative_int(
                self.next_sequence,
                "next_sequence",
                maximum=10_000_001,
            ),
        )
        if self.next_sequence < 1:
            raise TurnRuntimeError("next_sequence must be positive")
        if self.last_event_digest is not None:
            object.__setattr__(
                self,
                "last_event_digest",
                _sha256(self.last_event_digest, "last_event_digest"),
            )
        if self.pending_tool_side_effect is not None and not isinstance(
            self.pending_tool_side_effect, SideEffectClass
        ):
            object.__setattr__(
                self,
                "pending_tool_side_effect",
                SideEffectClass(str(self.pending_tool_side_effect)),
            )
        if self.failure_class is not None and not isinstance(
            self.failure_class, FailureClass
        ):
            object.__setattr__(
                self, "failure_class", FailureClass(str(self.failure_class))
            )
        BudgetGovernor.require_within(self.budget, self.usage)

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def has_ambiguous_external_effect(self) -> bool:
        return (
            self.state is TurnState.TOOL_EXECUTING
            and self.pending_tool_side_effect in _CONSEQUENTIAL_EFFECTS
            and self.external_effect_started
            and not self.pending_tool_receipt_ref
        )

    def apply(self, event: TurnEvent) -> "TurnSnapshot":
        if self.terminal:
            raise TurnRuntimeError("cannot append event to terminal turn")
        if event.operation_id != self.operation_id:
            raise TurnRuntimeError("event belongs to a different operation")
        if event.request_digest != self.request_digest:
            raise TurnRuntimeError("event request digest does not match operation")
        if event.sequence != self.next_sequence:
            raise TurnRuntimeError("event sequence is not the next durable sequence")
        if event.from_state is not self.state:
            raise TurnRuntimeError("event from_state does not match snapshot state")
        if event.previous_event_digest != self.last_event_digest:
            raise TurnRuntimeError("event digest chain is broken")

        next_usage = self.usage if event.usage is None else event.usage
        BudgetGovernor.require_within(self.budget, next_usage)

        tool_call_id = self.pending_tool_call_id
        tool_side_effect = self.pending_tool_side_effect
        tool_receipt_ref = self.pending_tool_receipt_ref
        external_effect_started = self.external_effect_started

        if event.to_state is TurnState.TOOL_EXECUTING:
            tool_call_id = event.tool_call_id
            tool_side_effect = event.tool_side_effect
            tool_receipt_ref = event.tool_receipt_ref
            external_effect_started = bool(event.external_effect_started)
        elif self.state is TurnState.TOOL_EXECUTING:
            if event.tool_receipt_ref is not None:
                tool_receipt_ref = event.tool_receipt_ref
            if (
                tool_side_effect in _CONSEQUENTIAL_EFFECTS
                and external_effect_started
                and tool_receipt_ref is None
                and event.tool_reconciliation_ref is None
                and event.to_state
                in {
                    TurnState.TOOL_REQUIRED,
                    TurnState.MODEL_RUNNING,
                    TurnState.VERIFYING,
                    TurnState.FAILED_RETRYABLE,
                    TurnState.CANCELLED,
                }
            ):
                raise TurnRuntimeError(
                    "ambiguous consequential tool effect must be reconciled "
                    "before retry, continuation, or cancellation"
                )
            if event.to_state not in {
                TurnState.DEGRADED,
                TurnState.FAILED_TERMINAL,
                TurnState.QUARANTINED,
            }:
                tool_call_id = None
                tool_side_effect = None
                tool_receipt_ref = None
                external_effect_started = False

        return TurnSnapshot(
            operation_id=self.operation_id,
            request_digest=self.request_digest,
            thread_id=self.thread_id,
            causal_user_message_id=self.causal_user_message_id,
            state=event.to_state,
            budget=self.budget,
            usage=next_usage,
            next_sequence=event.sequence + 1,
            last_event_digest=event.digest,
            pending_tool_call_id=tool_call_id,
            pending_tool_side_effect=tool_side_effect,
            pending_tool_receipt_ref=tool_receipt_ref,
            external_effect_started=external_effect_started,
            provider_receipt_ref=(
                event.provider_receipt_ref
                if event.provider_receipt_ref is not None
                else self.provider_receipt_ref
            ),
            failure_class=event.failure_class,
        )


def start_turn(
    *,
    operation_id: str,
    request_digest: str,
    thread_id: str,
    causal_user_message_id: str,
    budget: ExecutionBudget | None = None,
) -> TurnSnapshot:
    return TurnSnapshot(
        operation_id=operation_id,
        request_digest=request_digest,
        thread_id=thread_id,
        causal_user_message_id=causal_user_message_id,
        state=TurnState.RECEIVED,
        budget=budget or ExecutionBudget(),
    )


def make_event(
    snapshot: TurnSnapshot,
    to_state: TurnState,
    *,
    observed_at: datetime,
    reason_code: str = "advance",
    failure_class: FailureClass | None = None,
    tool_call_id: str | None = None,
    tool_side_effect: SideEffectClass | None = None,
    tool_receipt_ref: str | None = None,
    tool_reconciliation_ref: str | None = None,
    external_effect_started: bool = False,
    provider_receipt_ref: str | None = None,
    usage: BudgetUsage | None = None,
    payload: Mapping[str, object] | None = None,
) -> TurnEvent:
    return TurnEvent(
        operation_id=snapshot.operation_id,
        request_digest=snapshot.request_digest,
        sequence=snapshot.next_sequence,
        from_state=snapshot.state,
        to_state=to_state,
        observed_at=observed_at,
        previous_event_digest=snapshot.last_event_digest,
        reason_code=reason_code,
        failure_class=failure_class,
        tool_call_id=tool_call_id,
        tool_side_effect=tool_side_effect,
        tool_receipt_ref=tool_receipt_ref,
        tool_reconciliation_ref=tool_reconciliation_ref,
        external_effect_started=external_effect_started,
        provider_receipt_ref=provider_receipt_ref,
        usage=usage,
        payload={} if payload is None else payload,
    )


class TurnJournal:
    """Pure replay helper for durable operation journals."""

    @staticmethod
    def replay(
        initial: TurnSnapshot,
        events: Iterable[TurnEvent],
    ) -> TurnSnapshot:
        snapshot = initial
        for event in events:
            snapshot = snapshot.apply(event)
        return snapshot

    @staticmethod
    def verify(
        initial: TurnSnapshot,
        events: Iterable[TurnEvent],
    ) -> tuple[TurnSnapshot, tuple[str, ...]]:
        snapshot = initial
        errors: list[str] = []
        for index, event in enumerate(events, start=1):
            try:
                snapshot = snapshot.apply(event)
            except (TurnRuntimeError, ValueError) as exc:
                errors.append(f"event[{index}]: {exc}")
                break
        return snapshot, tuple(errors)


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    action: RecoveryAction
    reason_code: str
    safe_to_retry: bool
    requires_receipt_reconciliation: bool = False


class RecoveryPlanner:
    """Deterministic restart behavior from durable turn state."""

    @staticmethod
    def plan(snapshot: TurnSnapshot) -> RecoveryDecision:
        if snapshot.terminal:
            return RecoveryDecision(
                RecoveryAction.NOOP_TERMINAL,
                "terminal-state",
                safe_to_retry=False,
            )
        if snapshot.has_ambiguous_external_effect:
            return RecoveryDecision(
                RecoveryAction.RECONCILE_TOOL,
                "ambiguous-consequential-tool-effect",
                safe_to_retry=False,
                requires_receipt_reconciliation=True,
            )

        state = snapshot.state
        if state is TurnState.RECEIVED:
            return RecoveryDecision(
                RecoveryAction.RESUME_ADMISSION,
                "admission-not-committed",
                safe_to_retry=True,
            )
        if state is TurnState.ADMITTED:
            return RecoveryDecision(
                RecoveryAction.RESUME_MESSAGE_COMMIT,
                "user-message-not-committed",
                safe_to_retry=True,
            )
        if state is TurnState.USER_MESSAGE_COMMITTED:
            return RecoveryDecision(
                RecoveryAction.RESUME_CONTEXT,
                "context-not-started",
                safe_to_retry=True,
            )
        if state is TurnState.CONTEXT_COMPILING:
            return RecoveryDecision(
                RecoveryAction.RESUME_CONTEXT,
                "context-compilation-incomplete",
                safe_to_retry=True,
            )
        if state is TurnState.ROUTING:
            return RecoveryDecision(
                RecoveryAction.RESUME_ROUTING,
                "routing-incomplete",
                safe_to_retry=True,
            )
        if state is TurnState.MODEL_RUNNING:
            return RecoveryDecision(
                RecoveryAction.RETRY_MODEL,
                "model-result-not-authoritative",
                safe_to_retry=True,
            )
        if state is TurnState.TOOL_REQUIRED:
            return RecoveryDecision(
                RecoveryAction.RESUME_TOOL_ADMISSION,
                "tool-proposal-not-executing",
                safe_to_retry=True,
            )
        if state is TurnState.AWAITING_USER:
            return RecoveryDecision(
                RecoveryAction.WAIT_FOR_USER,
                "user-decision-required",
                safe_to_retry=False,
            )
        if state is TurnState.TOOL_EXECUTING:
            if snapshot.pending_tool_receipt_ref:
                return RecoveryDecision(
                    RecoveryAction.RESUME_VERIFICATION,
                    "durable-tool-receipt-present",
                    safe_to_retry=False,
                )
            return RecoveryDecision(
                RecoveryAction.RETRY_TOOL,
                "tool-has-no-consequential-ambiguity",
                safe_to_retry=True,
            )
        if state is TurnState.VERIFYING:
            return RecoveryDecision(
                RecoveryAction.RESUME_VERIFICATION,
                "verification-incomplete",
                safe_to_retry=True,
            )
        if state is TurnState.FINALIZING:
            return RecoveryDecision(
                RecoveryAction.RESUME_FINALIZATION,
                "assistant-message-not-committed",
                safe_to_retry=True,
            )
        if state is TurnState.ASSISTANT_MESSAGE_COMMITTED:
            return RecoveryDecision(
                RecoveryAction.RESUME_MEMORY,
                "response-is-authoritative-memory-is-not",
                safe_to_retry=False,
            )
        if state is TurnState.MEMORY_PROPOSAL:
            return RecoveryDecision(
                RecoveryAction.FINALIZE_COMPLETE,
                "optional-memory-proposal-pending",
                safe_to_retry=False,
            )
        raise TurnRuntimeError(f"unhandled recovery state: {state.value}")


def execution_budget_from_dict(raw: Mapping[str, object]) -> ExecutionBudget:
    """Decode the canonical execution-budget wire shape."""

    if not isinstance(raw, Mapping):
        raise TurnRuntimeError("execution budget must be an object")
    required = set(ExecutionBudget().as_dict())
    if set(raw) != required:
        raise TurnRuntimeError("execution budget fields drifted")
    return ExecutionBudget(**{key: raw[key] for key in required})


def budget_usage_from_dict(raw: Mapping[str, object]) -> BudgetUsage:
    """Decode the canonical budget-usage wire shape."""

    if not isinstance(raw, Mapping):
        raise TurnRuntimeError("budget usage must be an object")
    required = set(BudgetUsage().as_dict())
    if set(raw) != required:
        raise TurnRuntimeError("budget usage fields drifted")
    return BudgetUsage(**{key: raw[key] for key in required})


def turn_event_from_dict(raw: Mapping[str, object]) -> TurnEvent:
    """Decode one canonical durable turn event."""

    if not isinstance(raw, Mapping):
        raise TurnRuntimeError("turn event must be an object")
    version = raw.get("schema_version")
    if version != CHAT_TURN_SCHEMA_VERSION:
        raise TurnRuntimeError("unsupported turn event schema version")
    observed_raw = raw.get("observed_at")
    if not isinstance(observed_raw, str):
        raise TurnRuntimeError("turn event observed_at must be ISO text")
    try:
        observed_at = datetime.fromisoformat(observed_raw)
    except ValueError as exc:
        raise TurnRuntimeError("turn event observed_at is invalid") from exc
    usage_raw = raw.get("usage")
    return TurnEvent(
        operation_id=raw.get("operation_id"),
        request_digest=raw.get("request_digest"),
        sequence=raw.get("sequence"),
        from_state=raw.get("from_state"),
        to_state=raw.get("to_state"),
        observed_at=observed_at,
        previous_event_digest=raw.get("previous_event_digest"),
        reason_code=raw.get("reason_code", "advance"),
        failure_class=raw.get("failure_class"),
        tool_call_id=raw.get("tool_call_id"),
        tool_side_effect=raw.get("tool_side_effect"),
        tool_receipt_ref=raw.get("tool_receipt_ref"),
        tool_reconciliation_ref=raw.get("tool_reconciliation_ref"),
        external_effect_started=bool(raw.get("external_effect_started")),
        provider_receipt_ref=raw.get("provider_receipt_ref"),
        usage=(
            None
            if usage_raw is None
            else budget_usage_from_dict(usage_raw)
        ),
        payload=raw.get("payload") or {},
    )


def turn_snapshot_dict(snapshot: TurnSnapshot) -> dict[str, object]:
    """Canonical materialized snapshot representation."""

    if not isinstance(snapshot, TurnSnapshot):
        raise TurnRuntimeError("snapshot must be TurnSnapshot")
    return {
        "schema_version": CHAT_TURN_SCHEMA_VERSION,
        "operation_id": snapshot.operation_id,
        "request_digest": snapshot.request_digest,
        "thread_id": snapshot.thread_id,
        "causal_user_message_id": snapshot.causal_user_message_id,
        "state": snapshot.state.value,
        "budget": snapshot.budget.as_dict(),
        "usage": snapshot.usage.as_dict(),
        "next_sequence": snapshot.next_sequence,
        "last_event_digest": snapshot.last_event_digest,
        "pending_tool_call_id": snapshot.pending_tool_call_id,
        "pending_tool_side_effect": (
            None
            if snapshot.pending_tool_side_effect is None
            else snapshot.pending_tool_side_effect.value
        ),
        "pending_tool_receipt_ref": snapshot.pending_tool_receipt_ref,
        "external_effect_started": snapshot.external_effect_started,
        "provider_receipt_ref": snapshot.provider_receipt_ref,
        "failure_class": (
            None if snapshot.failure_class is None else snapshot.failure_class.value
        ),
    }


def turn_snapshot_from_dict(raw: Mapping[str, object]) -> TurnSnapshot:
    """Decode the canonical materialized snapshot representation."""

    if not isinstance(raw, Mapping):
        raise TurnRuntimeError("turn snapshot must be an object")
    if raw.get("schema_version") != CHAT_TURN_SCHEMA_VERSION:
        raise TurnRuntimeError("unsupported turn snapshot schema version")
    budget_raw = raw.get("budget")
    usage_raw = raw.get("usage")
    if not isinstance(budget_raw, Mapping):
        raise TurnRuntimeError("turn snapshot budget must be an object")
    if not isinstance(usage_raw, Mapping):
        raise TurnRuntimeError("turn snapshot usage must be an object")
    return TurnSnapshot(
        operation_id=raw.get("operation_id"),
        request_digest=raw.get("request_digest"),
        thread_id=raw.get("thread_id"),
        causal_user_message_id=raw.get("causal_user_message_id"),
        state=raw.get("state"),
        budget=execution_budget_from_dict(budget_raw),
        usage=budget_usage_from_dict(usage_raw),
        next_sequence=raw.get("next_sequence"),
        last_event_digest=raw.get("last_event_digest"),
        pending_tool_call_id=raw.get("pending_tool_call_id"),
        pending_tool_side_effect=raw.get("pending_tool_side_effect"),
        pending_tool_receipt_ref=raw.get("pending_tool_receipt_ref"),
        external_effect_started=bool(raw.get("external_effect_started")),
        provider_receipt_ref=raw.get("provider_receipt_ref"),
        failure_class=raw.get("failure_class"),
    )


def operation_digest(snapshot: TurnSnapshot) -> str:
    """Stable digest suitable for exact-head/runtime evidence receipts."""

    return digest_json(turn_snapshot_dict(snapshot))


__all__ = [
    "CHAT_TURN_SCHEMA_VERSION",
    "BudgetDecision",
    "BudgetGovernor",
    "BudgetUsage",
    "ExecutionBudget",
    "FailureClass",
    "RecoveryAction",
    "RecoveryDecision",
    "RecoveryPlanner",
    "TERMINAL_STATES",
    "TurnEvent",
    "TurnJournal",
    "TurnRuntimeError",
    "TurnSnapshot",
    "TurnState",
    "budget_usage_from_dict",
    "execution_budget_from_dict",
    "make_event",
    "operation_digest",
    "start_turn",
    "turn_event_from_dict",
    "turn_snapshot_dict",
    "turn_snapshot_from_dict",
]
