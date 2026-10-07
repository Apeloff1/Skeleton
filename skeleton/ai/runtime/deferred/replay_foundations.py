"""Isolation, replay and deterministic foundation contracts VOL-293..299."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class BulkheadLimit:
    concurrency: int
    capacity: int


@dataclass(frozen=True, slots=True)
class Bulkhead:
    bulkhead_id: str
    domain: str
    limit: BulkheadLimit
    active: int


@dataclass(frozen=True, slots=True)
class OverflowDecision:
    admitted: bool
    target_bulkhead: str | None
    reason: str


def overflow(
    source: Bulkhead,
    target: Bulkhead | None,
    *,
    authority_compatible: bool,
) -> OverflowDecision:
    for bulkhead in (source,) + ((target,) if target else ()):
        if (
            not bulkhead.bulkhead_id
            or not bulkhead.domain
            or bulkhead.limit.concurrency < 1
            or bulkhead.limit.capacity < 1
            or bulkhead.active < 0
            or bulkhead.active > bulkhead.limit.capacity
        ):
            raise ValueError("invalid bulkhead state")
    if target and target.bulkhead_id == source.bulkhead_id:
        raise ValueError("overflow target must be distinct")
    if source.active < source.limit.concurrency:
        return OverflowDecision(True, source.bulkhead_id, "source capacity")
    if (
        target
        and authority_compatible
        and target.active < target.limit.concurrency
    ):
        return OverflowDecision(True, target.bulkhead_id, "explicit overflow")
    return OverflowDecision(False, None, "isolated capacity exhausted")


@dataclass(frozen=True, slots=True)
class DeadLetter:
    operation_id: str
    payload_digest: str
    attempts: int
    failure_cause: str
    idempotency_key: str | None


@dataclass(frozen=True, slots=True)
class ReplayAuthorization:
    operation_id: str
    current_authorization: bool
    compatibility_verified: bool
    idempotency_verified: bool


class DeadLetterDisposition(str, Enum):
    HOLD = "hold"
    REPLAY = "replay"
    DISCARD = "discard"


def dead_letter_disposition(
    dead_letter: DeadLetter,
    authorization: ReplayAuthorization,
) -> DeadLetterDisposition:
    if (
        not all(
            (
                dead_letter.operation_id,
                dead_letter.payload_digest,
                dead_letter.failure_cause,
                authorization.operation_id,
            )
        )
        or dead_letter.attempts < 0
    ):
        return DeadLetterDisposition.HOLD
    if dead_letter.operation_id != authorization.operation_id:
        return DeadLetterDisposition.HOLD
    if (
        authorization.current_authorization
        and authorization.compatibility_verified
        and authorization.idempotency_verified
    ):
        return DeadLetterDisposition.REPLAY
    return DeadLetterDisposition.HOLD


class ReplayMode(str, Enum):
    RECONSTRUCT = "reconstruct"
    SIMULATE = "simulate"
    REAL_EFFECT = "real_effect"


@dataclass(frozen=True, slots=True)
class ReplayRequest:
    operation_id: str
    mode: ReplayMode
    reconciled: bool = False
    idempotent: bool = False


@dataclass(frozen=True, slots=True)
class ReplayResult:
    operation_id: str
    allowed: bool
    external_effects: bool
    reason: str


def replay(request: ReplayRequest) -> ReplayResult:
    if not request.operation_id:
        return ReplayResult(
            request.operation_id,
            False,
            False,
            "operation identity required",
        )
    if request.mode is not ReplayMode.REAL_EFFECT:
        return ReplayResult(request.operation_id, True, False, request.mode.value)
    allowed = request.reconciled and request.idempotent
    return ReplayResult(
        request.operation_id,
        allowed,
        allowed,
        (
            "effect replay admitted"
            if allowed
            else "effect replay requires reconciliation and idempotency"
        ),
    )


class DeterminismClass(str, Enum):
    EXACT = "exact"
    TOLERANT = "tolerant"
    NONDETERMINISTIC = "nondeterministic"


@dataclass(frozen=True, slots=True)
class VariancePolicy:
    absolute_tolerance: float
    relative_tolerance: float


@dataclass(frozen=True, slots=True)
class DeterminismEnvelope:
    classification: DeterminismClass
    seed: int | None
    variance: VariancePolicy
    nondeterminism_sources: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.variance.absolute_tolerance < 0
            or self.variance.relative_tolerance < 0
        ):
            raise ValueError("variance tolerance must be nonnegative")
        if (
            any(not source for source in self.nondeterminism_sources)
            or len(set(self.nondeterminism_sources))
            != len(self.nondeterminism_sources)
        ):
            raise ValueError("unique nondeterminism sources required")
        if (
            self.classification is DeterminismClass.EXACT
            and self.nondeterminism_sources
        ):
            raise ValueError("exact envelope cannot declare nondeterminism")

    def equivalent(self, left: float, right: float) -> bool:
        if self.classification is DeterminismClass.EXACT:
            return left == right
        if self.classification is DeterminismClass.NONDETERMINISTIC:
            return False
        return abs(left - right) <= max(
            self.variance.absolute_tolerance,
            self.variance.relative_tolerance * max(abs(left), abs(right)),
        )


@dataclass(frozen=True, slots=True)
class Instant:
    unix_ns: int
    timezone: str | None = None


@dataclass(frozen=True, slots=True)
class Duration:
    monotonic_ns: int

    def __post_init__(self) -> None:
        if self.monotonic_ns < 0:
            raise ValueError("duration must be monotonic/non-negative")


@dataclass(frozen=True, slots=True)
class Deadline:
    start_monotonic_ns: int
    duration: Duration

    def __post_init__(self) -> None:
        if self.start_monotonic_ns < 0:
            raise ValueError("deadline start must be nonnegative")

    def expired(self, now_monotonic_ns: int) -> bool:
        if now_monotonic_ns < 0:
            raise ValueError("monotonic clock must be nonnegative")
        return (
            now_monotonic_ns - self.start_monotonic_ns
            >= self.duration.monotonic_ns
        )


class IdentifierKind(str, Enum):
    OPERATION = "operation"
    PRINCIPAL = "principal"
    RESOURCE = "resource"


@dataclass(frozen=True, slots=True)
class Identifier:
    kind: IdentifierKind
    value: str


class IdentifierCodec:
    @staticmethod
    def parse(text: str) -> Identifier:
        if (
            text != text.strip()
            or text.lower() != text
            or text.count(":") != 1
        ):
            raise ValueError("ambiguous identifier")
        kind, value = text.split(":")
        if not value or any(char.isspace() for char in value):
            raise ValueError("ambiguous identifier")
        return Identifier(IdentifierKind(kind), value)

    @staticmethod
    def render(identifier: Identifier) -> str:
        return f"{identifier.kind.value}:{identifier.value}"


@dataclass(frozen=True, slots=True)
class SequenceNumber:
    domain: str
    value: int

    def __post_init__(self) -> None:
        if not self.domain or self.value < 0:
            raise ValueError("valid sequence identity required")


@dataclass(frozen=True, slots=True)
class LogicalClock:
    node_id: str
    counter: int

    def __post_init__(self) -> None:
        if not self.node_id or self.counter < 0:
            raise ValueError("valid logical clock required")

    def tick(self) -> "LogicalClock":
        return LogicalClock(self.node_id, self.counter + 1)


class CausalRelation(str, Enum):
    BEFORE = "before"
    AFTER = "after"
    CONCURRENT = "concurrent"
    UNKNOWN = "unknown"


def compare_sequence(
    left: SequenceNumber,
    right: SequenceNumber,
) -> CausalRelation:
    if left.domain != right.domain:
        return CausalRelation.UNKNOWN
    if left.value < right.value:
        return CausalRelation.BEFORE
    if left.value > right.value:
        return CausalRelation.AFTER
    return CausalRelation.CONCURRENT
