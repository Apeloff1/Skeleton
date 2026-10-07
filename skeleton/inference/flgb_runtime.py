"""FLGB-01 provider-neutral inference runtime contracts.

The module is deliberately deterministic and provider-neutral. It owns no
tool execution authority; it only validates, records, and derives receipts
for an inference operation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
import threading
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from .session import InferenceUsage, ModelRequest

MAX_ID_CHARS = 256
MAX_TEXT_CHARS = 1_000_000
MAX_JSON_BYTES = 2_000_000
MAX_JSON_NODES = 50_000
MAX_JSON_DEPTH = 64
MAX_STREAM_BUFFER_BYTES = 2_000_000
MAX_STREAM_EVENTS = 4096
MAX_TOOL_ARGS_BYTES = 1_000_000
MAX_PROVIDER_CANDIDATES = 16
MAX_USAGE_TOKENS = 2_000_000_000
MAX_COST_MICRO_UNITS = 10**15


class FLGBInferenceError(ValueError):
    """Base fail-closed contract error for FLGB-01."""


class CancelledError(RuntimeError):
    """Raised when a cancellation boundary is crossed."""


class DeadlineExceeded(RuntimeError):
    """Raised when a deadline budget is exhausted."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def require_id(value: str, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_ID_CHARS:
        raise FLGBInferenceError(f"invalid {name}")
    if any(ord(ch) < 32 for ch in value):
        raise FLGBInferenceError(f"invalid {name}")
    return value


def require_digest(value: str, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise FLGBInferenceError(f"invalid {name}")
    return value


def canonical_bytes(value: Any) -> bytes:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FLGBInferenceError("value is not canonical-json encodable") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise FLGBInferenceError("canonical payload exceeds byte budget")
    return raw


def digest_json(value: Any) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def _copy_mapping(value: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FLGBInferenceError(f"{name} must be a mapping")
    copied = dict(value)
    for key in copied:
        if not isinstance(key, str) or not key:
            raise FLGBInferenceError(f"{name} keys must be non-empty strings")
    canonical_bytes(copied)
    return MappingProxyType(copied)


@dataclass(frozen=True)
class OperationEnvelope:
    operation_id: str
    request_digest: str
    authority_scope: str
    deadline_ms: int
    max_output_tokens: int
    idempotency_key: str
    budget_class: str = "interactive"

    def __post_init__(self) -> None:
        require_id(self.operation_id, "operation_id")
        require_digest(self.request_digest, "request_digest")
        require_id(self.authority_scope, "authority_scope")
        require_id(self.idempotency_key, "idempotency_key")
        if not _is_int(self.deadline_ms) or not 1 <= self.deadline_ms <= 86_400_000:
            raise FLGBInferenceError("deadline_ms out of bounds")
        if not _is_int(self.max_output_tokens) or not 1 <= self.max_output_tokens <= 1_000_000:
            raise FLGBInferenceError("max_output_tokens out of bounds")
        if self.budget_class not in {"interactive", "batch", "evaluation", "recovery"}:
            raise FLGBInferenceError("invalid budget_class")
        if self.authority_scope != "inference-proposal-only":
            raise FLGBInferenceError("inference envelope cannot grant execution authority")

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "operation_id": self.operation_id,
                "request_digest": self.request_digest,
                "authority_scope": self.authority_scope,
                "deadline_ms": self.deadline_ms,
                "max_output_tokens": self.max_output_tokens,
                "idempotency_key": self.idempotency_key,
                "budget_class": self.budget_class,
            }
        )


@dataclass(frozen=True)
class ConversationTurn:
    sequence: int
    role: str
    content_digest: str
    content_chars: int

    def __post_init__(self) -> None:
        if not _is_int(self.sequence) or self.sequence < 0:
            raise FLGBInferenceError("invalid conversation sequence")
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise FLGBInferenceError("invalid conversation role")
        require_digest(self.content_digest, "content_digest")
        if not _is_int(self.content_chars) or not 0 <= self.content_chars <= MAX_TEXT_CHARS:
            raise FLGBInferenceError("invalid content_chars")


@dataclass(frozen=True)
class ConversationState:
    conversation_id: str
    revision: int = 0
    turns: tuple[ConversationTurn, ...] = ()
    max_turns: int = 4096

    def __post_init__(self) -> None:
        require_id(self.conversation_id, "conversation_id")
        if not _is_int(self.revision) or self.revision < 0:
            raise FLGBInferenceError("invalid revision")
        if not _is_int(self.max_turns) or not 1 <= self.max_turns <= 4096:
            raise FLGBInferenceError("invalid max_turns")
        if len(self.turns) > self.max_turns:
            raise FLGBInferenceError("conversation turn budget exceeded")
        for index, turn in enumerate(self.turns):
            if not isinstance(turn, ConversationTurn) or turn.sequence != index:
                raise FLGBInferenceError("conversation sequence drift")
        if self.revision != len(self.turns):
            raise FLGBInferenceError("revision must equal durable turn count")

    def append(self, role: str, content: str) -> "ConversationState":
        if not isinstance(content, str) or len(content) > MAX_TEXT_CHARS:
            raise FLGBInferenceError("invalid conversation content")
        if len(self.turns) >= self.max_turns:
            raise FLGBInferenceError("conversation turn budget exceeded")
        turn = ConversationTurn(
            sequence=len(self.turns),
            role=role,
            content_digest=sha256(content.encode("utf-8")).hexdigest(),
            content_chars=len(content),
        )
        return ConversationState(
            conversation_id=self.conversation_id,
            revision=self.revision + 1,
            turns=self.turns + (turn,),
            max_turns=self.max_turns,
        )

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "conversation_id": self.conversation_id,
                "revision": self.revision,
                "turns": [
                    {
                        "sequence": turn.sequence,
                        "role": turn.role,
                        "content_digest": turn.content_digest,
                        "content_chars": turn.content_chars,
                    }
                    for turn in self.turns
                ],
            }
        )


@dataclass(frozen=True)
class ProviderNeutralRequest:
    envelope: OperationEnvelope
    provider: str
    model: str
    conversation_digest: str
    input_digest: str
    temperature_milli: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, OperationEnvelope):
            raise FLGBInferenceError("OperationEnvelope required")
        require_id(self.provider, "provider")
        require_id(self.model, "model")
        require_digest(self.conversation_digest, "conversation_digest")
        require_digest(self.input_digest, "input_digest")
        if not _is_int(self.temperature_milli) or not 0 <= self.temperature_milli <= 2000:
            raise FLGBInferenceError("temperature_milli out of bounds")
        object.__setattr__(self, "metadata", _copy_mapping(self.metadata, "metadata"))

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "envelope_digest": self.envelope.digest,
                "provider": self.provider,
                "model": self.model,
                "conversation_digest": self.conversation_digest,
                "input_digest": self.input_digest,
                "temperature_milli": self.temperature_milli,
                "metadata": dict(self.metadata),
            }
        )

    def to_model_request(self) -> ModelRequest:
        return ModelRequest(
            operation_id=self.envelope.operation_id,
            request_digest=self.digest,
            model=self.model,
            provider=self.provider,
            max_output_tokens=self.envelope.max_output_tokens,
            deadline_ms=self.envelope.deadline_ms,
        )


def _no_duplicate_pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FLGBInferenceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json_shape(value: Any, depth: int = 0) -> tuple[int, int]:
    if depth > MAX_JSON_DEPTH:
        raise FLGBInferenceError("JSON nesting exceeds depth budget")
    nodes = 1
    max_depth = depth
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise FLGBInferenceError("JSON object key must be a string")
            child_nodes, child_depth = _json_shape(item, depth + 1)
            nodes += child_nodes
            max_depth = max(max_depth, child_depth)
    elif isinstance(value, list):
        for item in value:
            child_nodes, child_depth = _json_shape(item, depth + 1)
            nodes += child_nodes
            max_depth = max(max_depth, child_depth)
    elif isinstance(value, float) and not math.isfinite(value):
        raise FLGBInferenceError("non-finite JSON number")
    if nodes > MAX_JSON_NODES:
        raise FLGBInferenceError("JSON node budget exceeded")
    return nodes, max_depth


def parse_structured_output(
    raw: str,
    *,
    required_keys: Iterable[str] = (),
    allowed_keys: Iterable[str] | None = None,
) -> Mapping[str, Any]:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_JSON_BYTES:
        raise FLGBInferenceError("structured output exceeds byte budget")
    try:
        value = json.loads(raw, object_pairs_hook=_no_duplicate_pairs)
    except (json.JSONDecodeError, FLGBInferenceError) as exc:
        raise FLGBInferenceError("invalid structured JSON") from exc
    if not isinstance(value, dict):
        raise FLGBInferenceError("structured output must be a JSON object")
    _json_shape(value)
    required = tuple(required_keys)
    if any(not isinstance(key, str) or not key for key in required):
        raise FLGBInferenceError("required_keys malformed")
    missing = [key for key in required if key not in value]
    if missing:
        raise FLGBInferenceError(f"structured output missing keys: {missing}")
    if allowed_keys is not None:
        allowed = set(allowed_keys)
        extras = sorted(set(value) - allowed)
        if extras:
            raise FLGBInferenceError(f"structured output contains unapproved keys: {extras}")
    canonical_bytes(value)
    return MappingProxyType(value)


class StreamDecoder:
    """Bounded UTF-8 JSONL decoder with contiguous sequence enforcement."""

    def __init__(self, *, max_events: int = MAX_STREAM_EVENTS) -> None:
        if not _is_int(max_events) or not 1 <= max_events <= MAX_STREAM_EVENTS:
            raise FLGBInferenceError("invalid stream event budget")
        self.max_events = max_events
        self._buffer = bytearray()
        self._count = 0
        self._closed = False

    def feed(self, chunk: bytes) -> tuple[Mapping[str, Any], ...]:
        if self._closed:
            raise FLGBInferenceError("stream decoder is closed")
        if not isinstance(chunk, (bytes, bytearray)):
            raise FLGBInferenceError("stream chunk must be bytes")
        self._buffer.extend(chunk)
        if len(self._buffer) > MAX_STREAM_BUFFER_BYTES:
            raise FLGBInferenceError("stream buffer budget exceeded")
        decoded: list[Mapping[str, Any]] = []
        while b"\n" in self._buffer:
            line, _, remainder = self._buffer.partition(b"\n")
            self._buffer = bytearray(remainder)
            if not line:
                continue
            decoded.append(self._decode_line(bytes(line)))
        return tuple(decoded)

    def finalize(self) -> tuple[Mapping[str, Any], ...]:
        if self._closed:
            return ()
        self._closed = True
        if not self._buffer:
            return ()
        line = bytes(self._buffer)
        self._buffer.clear()
        return (self._decode_line(line),)

    def _decode_line(self, raw: bytes) -> Mapping[str, Any]:
        if self._count >= self.max_events:
            raise FLGBInferenceError("stream event budget exceeded")
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise FLGBInferenceError("invalid UTF-8 stream frame") from exc
        event = parse_structured_output(
            text,
            required_keys=("sequence", "kind", "payload"),
            allowed_keys=("sequence", "kind", "payload"),
        )
        if event["sequence"] != self._count:
            raise FLGBInferenceError("non-contiguous stream sequence")
        if event["kind"] not in {
            "text",
            "structured",
            "tool_call",
            "usage",
            "final",
            "cancelled",
            "error",
        }:
            raise FLGBInferenceError("invalid stream event kind")
        self._count += 1
        return event


@dataclass(frozen=True)
class ToolCallProposal:
    proposal_id: str
    operation_id: str
    tool_name: str
    arguments: Mapping[str, Any]
    requested_capabilities: tuple[str, ...] = ()
    authority_scope: str = "proposal-only"

    def __post_init__(self) -> None:
        require_id(self.proposal_id, "proposal_id")
        require_id(self.operation_id, "operation_id")
        require_id(self.tool_name, "tool_name")
        arguments = _copy_mapping(self.arguments, "arguments")
        if len(canonical_bytes(dict(arguments))) > MAX_TOOL_ARGS_BYTES:
            raise FLGBInferenceError("tool arguments exceed byte budget")
        object.__setattr__(self, "arguments", arguments)
        caps = tuple(self.requested_capabilities)
        if len(caps) > 64 or len(set(caps)) != len(caps):
            raise FLGBInferenceError("invalid requested capabilities")
        for cap in caps:
            require_id(cap, "capability")
        object.__setattr__(self, "requested_capabilities", caps)
        if self.authority_scope != "proposal-only":
            raise FLGBInferenceError("model tool proposal cannot self-authorize")

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "proposal_id": self.proposal_id,
                "operation_id": self.operation_id,
                "tool_name": self.tool_name,
                "arguments": dict(self.arguments),
                "requested_capabilities": list(self.requested_capabilities),
                "authority_scope": self.authority_scope,
            }
        )


class CancellationToken:
    def __init__(self, operation_id: str) -> None:
        self.operation_id = require_id(operation_id, "operation_id")
        self._event = threading.Event()
        self._reason: str | None = None
        self._lock = threading.Lock()

    def cancel(self, reason: str = "cancelled") -> bool:
        require_id(reason, "cancellation reason")
        with self._lock:
            if self._event.is_set():
                return False
            self._reason = reason
            self._event.set()
            return True

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str | None:
        return self._reason

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancelledError(self._reason or "cancelled")

    @property
    def receipt_digest(self) -> str:
        return digest_json(
            {
                "operation_id": self.operation_id,
                "cancelled": self.cancelled,
                "reason": self._reason,
            }
        )


@dataclass(frozen=True)
class DeadlineBudget:
    operation_id: str
    deadline_ms: int

    def __post_init__(self) -> None:
        require_id(self.operation_id, "operation_id")
        if not _is_int(self.deadline_ms) or not 1 <= self.deadline_ms <= 86_400_000:
            raise FLGBInferenceError("deadline_ms out of bounds")

    def remaining_ms(self, elapsed_ms: int) -> int:
        if not _is_int(elapsed_ms) or elapsed_ms < 0:
            raise FLGBInferenceError("elapsed_ms must be a non-negative integer")
        return max(0, self.deadline_ms - elapsed_ms)

    def require_remaining(self, elapsed_ms: int, reserve_ms: int = 0) -> int:
        if not _is_int(reserve_ms) or reserve_ms < 0:
            raise FLGBInferenceError("reserve_ms must be a non-negative integer")
        remaining = self.remaining_ms(elapsed_ms)
        if remaining <= reserve_ms:
            raise DeadlineExceeded(self.operation_id)
        return remaining - reserve_ms


@dataclass(frozen=True)
class UsageEntry:
    sequence: int
    input_tokens: int
    output_tokens: int
    cost_micro_units: int = 0

    def __post_init__(self) -> None:
        if not _is_int(self.sequence) or self.sequence < 0:
            raise FLGBInferenceError("invalid usage sequence")
        for name in ("input_tokens", "output_tokens"):
            value = getattr(self, name)
            if not _is_int(value) or not 0 <= value <= MAX_USAGE_TOKENS:
                raise FLGBInferenceError(f"invalid {name}")
        if not _is_int(self.cost_micro_units) or not 0 <= self.cost_micro_units <= MAX_COST_MICRO_UNITS:
            raise FLGBInferenceError("invalid cost_micro_units")


@dataclass(frozen=True)
class UsageLedger:
    operation_id: str
    entries: tuple[UsageEntry, ...] = ()

    def __post_init__(self) -> None:
        require_id(self.operation_id, "operation_id")
        for index, entry in enumerate(self.entries):
            if not isinstance(entry, UsageEntry) or entry.sequence != index:
                raise FLGBInferenceError("usage ledger sequence drift")

    def append(self, input_tokens: int, output_tokens: int, cost_micro_units: int = 0) -> "UsageLedger":
        entry = UsageEntry(len(self.entries), input_tokens, output_tokens, cost_micro_units)
        total_input = self.input_tokens + input_tokens
        total_output = self.output_tokens + output_tokens
        total_cost = self.cost_micro_units + cost_micro_units
        if total_input > MAX_USAGE_TOKENS or total_output > MAX_USAGE_TOKENS:
            raise FLGBInferenceError("aggregate token usage budget exceeded")
        if total_cost > MAX_COST_MICRO_UNITS:
            raise FLGBInferenceError("aggregate cost budget exceeded")
        return UsageLedger(self.operation_id, self.entries + (entry,))

    @property
    def input_tokens(self) -> int:
        return sum(entry.input_tokens for entry in self.entries)

    @property
    def output_tokens(self) -> int:
        return sum(entry.output_tokens for entry in self.entries)

    @property
    def cost_micro_units(self) -> int:
        return sum(entry.cost_micro_units for entry in self.entries)

    @property
    def usage(self) -> InferenceUsage:
        return InferenceUsage(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            attempts=max(1, len(self.entries)),
        )

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "operation_id": self.operation_id,
                "entries": [entry.__dict__ for entry in self.entries],
            }
        )


@dataclass(frozen=True)
class TerminalCommitReceipt:
    operation_id: str
    request_digest: str
    result_digest: str
    state_digest_before: str
    state_digest_after: str
    sequence: int
    idempotency_key: str
    terminal_reason: str

    def __post_init__(self) -> None:
        require_id(self.operation_id, "operation_id")
        require_digest(self.request_digest, "request_digest")
        require_digest(self.result_digest, "result_digest")
        require_digest(self.state_digest_before, "state_digest_before")
        require_digest(self.state_digest_after, "state_digest_after")
        require_id(self.idempotency_key, "idempotency_key")
        if not _is_int(self.sequence) or self.sequence < 0:
            raise FLGBInferenceError("invalid terminal sequence")
        if self.terminal_reason not in {
            "completed",
            "cancelled",
            "deadline",
            "provider_error",
            "policy_denied",
        }:
            raise FLGBInferenceError("invalid terminal reason")
        if self.terminal_reason != "completed" and self.state_digest_after != self.state_digest_before:
            raise FLGBInferenceError("failed terminal commit cannot mutate durable state")

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


@dataclass(frozen=True)
class ReplayReceipt:
    operation_id: str
    request_digest: str
    event_chain_digest: str
    result_digest: str
    terminal_commit_digest: str
    replay_generation: int = 0

    def __post_init__(self) -> None:
        require_id(self.operation_id, "operation_id")
        for name in (
            "request_digest",
            "event_chain_digest",
            "result_digest",
            "terminal_commit_digest",
        ):
            require_digest(getattr(self, name), name)
        if not _is_int(self.replay_generation) or not 0 <= self.replay_generation <= 1_000_000:
            raise FLGBInferenceError("invalid replay_generation")

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)

    def verifies(
        self,
        *,
        request_digest: str,
        event_chain_digest: str,
        result_digest: str,
        terminal_commit_digest: str,
    ) -> bool:
        return (
            self.request_digest == require_digest(request_digest, "request_digest")
            and self.event_chain_digest == require_digest(event_chain_digest, "event_chain_digest")
            and self.result_digest == require_digest(result_digest, "result_digest")
            and self.terminal_commit_digest
            == require_digest(terminal_commit_digest, "terminal_commit_digest")
        )


@dataclass(frozen=True)
class ProviderCandidate:
    provider: str
    model: str
    priority: int
    max_attempts: int = 1

    def __post_init__(self) -> None:
        require_id(self.provider, "provider")
        require_id(self.model, "model")
        if not _is_int(self.priority) or not 0 <= self.priority <= 1_000_000:
            raise FLGBInferenceError("invalid provider priority")
        if not _is_int(self.max_attempts) or not 1 <= self.max_attempts <= 8:
            raise FLGBInferenceError("invalid provider max_attempts")


@dataclass(frozen=True)
class FailoverAttempt:
    sequence: int
    provider: str
    model: str
    outcome: str

    def __post_init__(self) -> None:
        if not _is_int(self.sequence) or self.sequence < 0:
            raise FLGBInferenceError("invalid failover sequence")
        require_id(self.provider, "provider")
        require_id(self.model, "model")
        if self.outcome not in {
            "success",
            "timeout",
            "unavailable",
            "rate_limited",
            "provider_error",
            "cancelled",
            "policy_denied",
        }:
            raise FLGBInferenceError("invalid failover outcome")


class ProviderFailoverPlan:
    RETRYABLE = frozenset({"timeout", "unavailable", "rate_limited", "provider_error"})

    def __init__(self, candidates: Sequence[ProviderCandidate]) -> None:
        if not candidates or len(candidates) > MAX_PROVIDER_CANDIDATES:
            raise FLGBInferenceError("provider candidate set out of bounds")
        ordered = tuple(sorted(candidates, key=lambda item: (item.priority, item.provider, item.model)))
        identities = [(item.provider, item.model) for item in ordered]
        if len(set(identities)) != len(identities):
            raise FLGBInferenceError("duplicate provider candidate")
        self.candidates = ordered

    def choose(self, attempts: Sequence[FailoverAttempt]) -> ProviderCandidate | None:
        attempts = tuple(attempts)
        for index, attempt in enumerate(attempts):
            if not isinstance(attempt, FailoverAttempt) or attempt.sequence != index:
                raise FLGBInferenceError("failover attempt sequence drift")
            if attempt.outcome == "success":
                return None
            if attempt.outcome not in self.RETRYABLE:
                return None
        counts: dict[tuple[str, str], int] = {}
        for attempt in attempts:
            key = (attempt.provider, attempt.model)
            counts[key] = counts.get(key, 0) + 1
        for candidate in self.candidates:
            key = (candidate.provider, candidate.model)
            if counts.get(key, 0) < candidate.max_attempts:
                return candidate
        return None

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "candidates": [
                    {
                        "provider": item.provider,
                        "model": item.model,
                        "priority": item.priority,
                        "max_attempts": item.max_attempts,
                    }
                    for item in self.candidates
                ]
            }
        )
