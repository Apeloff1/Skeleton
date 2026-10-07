"""Persistent research agenda for Jeeves.

The epistemic frontier says what is unknown *now*.  A research agenda turns
those gaps into durable work across runs so expensive discoveries compound
instead of being forgotten when a single agent execution ends.

The agenda is deliberately deterministic and serializable.  It stores concise
research state, not private chain-of-thought: question identity, gap kind,
priority, attempts, evidence references, dependencies, and resolution state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .epistemic_frontier import FrontierSnapshot, GapKind
from .types import (
    AgentContractError,
    bounded_text,
    finite_number,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)


class AgendaStatus(str, Enum):
    QUEUED = "queued"
    ACTIVE = "active"
    BLOCKED = "blocked"
    RESOLVED = "resolved"
    DEFERRED = "deferred"


@dataclass(frozen=True, slots=True)
class ResearchAgendaPolicy:
    recurrence_bonus: float = 0.08
    attempt_bonus: float = 0.03
    age_bonus_per_day: float = 0.01
    maximum_age_bonus: float = 0.20
    resolution_information_gain_bits: float = 0.08
    reopen_surprise_bits: float = 2.5
    maximum_items: int = 5000
    maximum_attempts_before_defer: int = 8
    require_assurance_for_resolution: bool = False

    def __post_init__(self) -> None:
        for name in (
            "recurrence_bonus",
            "attempt_bonus",
            "age_bonus_per_day",
            "maximum_age_bonus",
            "resolution_information_gain_bits",
            "reopen_surprise_bits",
        ):
            value = finite_number(name, getattr(self, name))
            if value < 0:
                raise AgentContractError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "maximum_items",
            positive_int("maximum_items", self.maximum_items, maximum=1_000_000),
        )
        object.__setattr__(
            self,
            "maximum_attempts_before_defer",
            positive_int(
                "maximum_attempts_before_defer",
                self.maximum_attempts_before_defer,
                maximum=10_000,
            ),
        )
        if not isinstance(self.require_assurance_for_resolution, bool):
            raise AgentContractError("require_assurance_for_resolution must be boolean")


@dataclass(frozen=True, slots=True)
class AgendaItem:
    agenda_id: str
    obligation_id: str
    gap_id: str
    gap_kind: GapKind
    question: str
    base_priority: float
    status: AgendaStatus
    recurrence_count: int
    attempt_count: int
    cumulative_information_gain_bits: float
    maximum_surprise_bits: float
    evidence_refs: tuple[str, ...]
    dependencies: tuple[str, ...]
    created_at: float
    updated_at: float
    defer_until: float | None = None
    last_probe_id: str | None = None
    resolution_note: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("agenda_id", "obligation_id", "gap_id"):
            object.__setattr__(self, name, require_id(name, getattr(self, name)))
        if not isinstance(self.gap_kind, GapKind):
            object.__setattr__(self, "gap_kind", GapKind(str(self.gap_kind)))
        if not isinstance(self.status, AgendaStatus):
            object.__setattr__(self, "status", AgendaStatus(str(self.status)))
        object.__setattr__(
            self,
            "question",
            bounded_text("question", self.question, maximum=8192),
        )
        priority = finite_number("base_priority", self.base_priority)
        if priority < 0:
            raise AgentContractError("base_priority must be non-negative")
        object.__setattr__(self, "base_priority", priority)
        for name in ("recurrence_count", "attempt_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be non-negative integer")
        for name in (
            "cumulative_information_gain_bits",
            "maximum_surprise_bits",
            "created_at",
            "updated_at",
        ):
            value = finite_number(name, getattr(self, name))
            if name in {"cumulative_information_gain_bits", "maximum_surprise_bits"} and value < 0:
                raise AgentContractError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        if self.defer_until is not None:
            object.__setattr__(self, "defer_until", finite_number("defer_until", self.defer_until))
        object.__setattr__(
            self,
            "evidence_refs",
            tuple(sorted(set(require_id("evidence_ref", item) for item in self.evidence_refs))),
        )
        object.__setattr__(
            self,
            "dependencies",
            tuple(sorted(set(require_id("dependency", item) for item in self.dependencies))),
        )
        if self.last_probe_id is not None:
            object.__setattr__(self, "last_probe_id", require_id("last_probe_id", self.last_probe_id))
        object.__setattr__(
            self,
            "resolution_note",
            bounded_text(
                "resolution_note",
                self.resolution_note,
                maximum=4096,
                allow_empty=True,
            ),
        )
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(self.as_json())

    def as_json(self) -> dict[str, Any]:
        return {
            "agenda_id": self.agenda_id,
            "obligation_id": self.obligation_id,
            "gap_id": self.gap_id,
            "gap_kind": self.gap_kind.value,
            "question": self.question,
            "base_priority": self.base_priority,
            "status": self.status.value,
            "recurrence_count": self.recurrence_count,
            "attempt_count": self.attempt_count,
            "cumulative_information_gain_bits": self.cumulative_information_gain_bits,
            "maximum_surprise_bits": self.maximum_surprise_bits,
            "evidence_refs": list(self.evidence_refs),
            "dependencies": list(self.dependencies),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "defer_until": self.defer_until,
            "last_probe_id": self.last_probe_id,
            "resolution_note": self.resolution_note,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class RankedAgendaItem:
    item: AgendaItem
    effective_priority: float
    dependency_blocked: bool
    age_bonus: float
    recurrence_bonus: float
    attempt_bonus: float
    fingerprint: str


@dataclass(frozen=True, slots=True)
class AgendaSnapshot:
    items: tuple[AgendaItem, ...]
    ranked: tuple[RankedAgendaItem, ...]
    queued_count: int
    active_count: int
    blocked_count: int
    resolved_count: int
    deferred_count: int
    unresolved_priority: float
    fingerprint: str

    def as_json(self) -> dict[str, Any]:
        return {
            "items": [item.as_json() for item in self.items],
            "ranked": [
                {
                    "agenda_id": ranked.item.agenda_id,
                    "effective_priority": ranked.effective_priority,
                    "dependency_blocked": ranked.dependency_blocked,
                    "age_bonus": ranked.age_bonus,
                    "recurrence_bonus": ranked.recurrence_bonus,
                    "attempt_bonus": ranked.attempt_bonus,
                    "fingerprint": ranked.fingerprint,
                }
                for ranked in self.ranked
            ],
            "queued_count": self.queued_count,
            "active_count": self.active_count,
            "blocked_count": self.blocked_count,
            "resolved_count": self.resolved_count,
            "deferred_count": self.deferred_count,
            "unresolved_priority": self.unresolved_priority,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class AttemptResult:
    agenda_id: str
    previous_status: AgendaStatus
    status: AgendaStatus
    attempt_count: int
    information_gain_bits: float
    cumulative_information_gain_bits: float
    surprise_bits: float
    reopened: bool
    fingerprint: str


class ResearchAgenda:
    """Durable deterministic queue of Jeeves' unresolved research obligations."""

    def __init__(
        self,
        *,
        policy: ResearchAgendaPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.policy = policy or ResearchAgendaPolicy()
        self._clock = clock
        self._items: dict[str, AgendaItem] = {}

    def ingest_frontier(
        self,
        frontier: FrontierSnapshot,
        *,
        dependencies: Mapping[str, Sequence[str]] | None = None,
    ) -> AgendaSnapshot:
        if not isinstance(frontier, FrontierSnapshot):
            raise TypeError("frontier must be FrontierSnapshot")
        now = finite_number("now", self._clock())
        by_obligation = {item.obligation_id: item for item in frontier.obligations}
        probe_by_gap = {item.gap_id: item for item in frontier.probes}
        dependencies = dependencies or {}

        for gap in frontier.gaps:
            obligation = by_obligation[gap.obligation_id]
            agenda_id = stable_id(
                "research-agenda",
                {
                    "obligation": gap.obligation_id,
                    "kind": gap.kind.value,
                },
                length=30,
            )
            probe = probe_by_gap.get(gap.gap_id)
            probe_bonus = max(0.0, probe.score) * 0.05 if probe is not None else 0.0
            base_priority = (
                gap.severity * 0.65
                + gap.decision_impact * 0.30
                + probe_bonus
            )
            deps = tuple(dependencies.get(gap.obligation_id, ()))
            existing = self._items.get(agenda_id)
            if existing is None:
                self._items[agenda_id] = AgendaItem(
                    agenda_id=agenda_id,
                    obligation_id=gap.obligation_id,
                    gap_id=gap.gap_id,
                    gap_kind=gap.kind,
                    question=obligation.question,
                    base_priority=base_priority,
                    status=AgendaStatus.QUEUED,
                    recurrence_count=1,
                    attempt_count=0,
                    cumulative_information_gain_bits=0.0,
                    maximum_surprise_bits=0.0,
                    evidence_refs=gap.evidence_refs,
                    dependencies=deps,
                    created_at=now,
                    updated_at=now,
                    last_probe_id=probe.probe_id if probe is not None else None,
                    metadata={
                        "source_frontier": frontier.fingerprint,
                        "obligation_fingerprint": obligation.fingerprint,
                        "obligation_metadata": dict(obligation.metadata),
                        "gap_signal": gap.signal,
                        "gap_severity": gap.severity,
                    },
                )
            else:
                merged_refs = tuple(sorted(set(existing.evidence_refs) | set(gap.evidence_refs)))
                # A recurring unresolved gap is evidence that the question is
                # structurally sticky. Reopen resolved/deferred items and raise
                # their recurrence count instead of creating duplicates.
                next_status = existing.status
                defer_until = existing.defer_until
                if existing.status in {AgendaStatus.RESOLVED, AgendaStatus.DEFERRED}:
                    next_status = AgendaStatus.QUEUED
                    defer_until = None
                self._items[agenda_id] = replace(
                    existing,
                    gap_id=gap.gap_id,
                    question=obligation.question,
                    base_priority=max(existing.base_priority, base_priority),
                    status=next_status,
                    recurrence_count=existing.recurrence_count + 1,
                    evidence_refs=merged_refs,
                    dependencies=tuple(sorted(set(existing.dependencies) | set(deps))),
                    updated_at=now,
                    defer_until=defer_until,
                    last_probe_id=probe.probe_id if probe is not None else existing.last_probe_id,
                    metadata={
                        **dict(existing.metadata),
                        "source_frontier": frontier.fingerprint,
                        "obligation_fingerprint": obligation.fingerprint,
                        "obligation_metadata": dict(obligation.metadata),
                        "gap_signal": gap.signal,
                        "gap_severity": gap.severity,
                    },
                )

        self._trim()
        return self.snapshot()

    def rank(self, *, now: float | None = None) -> tuple[RankedAgendaItem, ...]:
        now = finite_number("now", self._clock() if now is None else now)
        resolved = {
            item.agenda_id
            for item in self._items.values()
            if item.status is AgendaStatus.RESOLVED
        }
        ranked: list[RankedAgendaItem] = []
        for item in self._items.values():
            if item.status is AgendaStatus.RESOLVED:
                continue
            if item.status is AgendaStatus.DEFERRED and item.defer_until is not None and item.defer_until > now:
                continue
            blocked = any(dep not in resolved for dep in item.dependencies)
            age_days = max(0.0, now - item.created_at) / 86400.0
            age_bonus = min(
                self.policy.maximum_age_bonus,
                age_days * self.policy.age_bonus_per_day,
            )
            recurrence_bonus = max(0, item.recurrence_count - 1) * self.policy.recurrence_bonus
            attempt_bonus = min(
                self.policy.maximum_age_bonus,
                item.attempt_count * self.policy.attempt_bonus,
            )
            priority = (
                item.base_priority
                + age_bonus
                + recurrence_bonus
                + attempt_bonus
            )
            if blocked:
                priority *= 0.1
            payload = {
                "agenda": item.fingerprint,
                "priority": priority,
                "blocked": blocked,
                "age_bonus": age_bonus,
                "recurrence_bonus": recurrence_bonus,
                "attempt_bonus": attempt_bonus,
            }
            ranked.append(
                RankedAgendaItem(
                    item=item,
                    effective_priority=priority,
                    dependency_blocked=blocked,
                    age_bonus=age_bonus,
                    recurrence_bonus=recurrence_bonus,
                    attempt_bonus=attempt_bonus,
                    fingerprint=stable_fingerprint(payload),
                )
            )
        ranked.sort(
            key=lambda value: (
                value.dependency_blocked,
                -value.effective_priority,
                value.item.agenda_id,
            )
        )
        return tuple(ranked)

    def claim_next(self) -> AgendaItem | None:
        now = finite_number("now", self._clock())
        for ranked in self.rank(now=now):
            if ranked.dependency_blocked:
                continue
            item = ranked.item
            updated = replace(
                item,
                status=AgendaStatus.ACTIVE,
                updated_at=now,
                defer_until=None,
            )
            self._items[item.agenda_id] = updated
            return updated
        return None

    def record_attempt(
        self,
        agenda_id: str,
        *,
        information_gain_bits: float,
        surprise_bits: float = 0.0,
        evidence_refs: Sequence[str] = (),
        successful: bool = True,
        resolution_note: str = "",
        defer_seconds: float | None = None,
        completion_certificate_id: str | None = None,
        completion_accepted: bool = False,
    ) -> AttemptResult:
        agenda_id = require_id("agenda_id", agenda_id)
        try:
            item = self._items[agenda_id]
        except KeyError as exc:
            raise AgentContractError("unknown agenda_id") from exc
        info = finite_number("information_gain_bits", information_gain_bits)
        surprise = finite_number("surprise_bits", surprise_bits)
        if info < 0 or surprise < 0:
            raise AgentContractError("information gain and surprise must be non-negative")
        now = finite_number("now", self._clock())
        refs = tuple(sorted(set(item.evidence_refs) | {
            require_id("evidence_ref", ref) for ref in evidence_refs
        }))
        attempts = item.attempt_count + 1
        cumulative = item.cumulative_information_gain_bits + info
        maximum_surprise = max(item.maximum_surprise_bits, surprise)

        previous_status = item.status
        reopened = False
        if completion_certificate_id is not None:
            completion_certificate_id = require_id(
                "completion_certificate_id",
                completion_certificate_id,
            )
        if not isinstance(completion_accepted, bool):
            raise AgentContractError("completion_accepted must be boolean")
        assurance_ready = (
            completion_accepted
            and completion_certificate_id is not None
        )
        if (
            successful
            and info >= self.policy.resolution_information_gain_bits
            and (
                assurance_ready
                or not self.policy.require_assurance_for_resolution
            )
        ):
            status = AgendaStatus.RESOLVED
            defer_until_value = None
        elif attempts >= self.policy.maximum_attempts_before_defer:
            status = AgendaStatus.DEFERRED
            defer_until_value = (
                now + max(0.0, finite_number("defer_seconds", defer_seconds))
                if defer_seconds is not None
                else None
            )
        elif defer_seconds is not None:
            seconds = finite_number("defer_seconds", defer_seconds)
            if seconds < 0:
                raise AgentContractError("defer_seconds must be non-negative")
            status = AgendaStatus.DEFERRED
            defer_until_value = now + seconds
        else:
            status = AgendaStatus.QUEUED
            defer_until_value = None

        if surprise >= self.policy.reopen_surprise_bits and previous_status is AgendaStatus.RESOLVED:
            status = AgendaStatus.QUEUED
            defer_until_value = None
            reopened = True

        updated = replace(
            item,
            status=status,
            attempt_count=attempts,
            cumulative_information_gain_bits=cumulative,
            maximum_surprise_bits=maximum_surprise,
            evidence_refs=refs,
            updated_at=now,
            defer_until=defer_until_value,
            resolution_note=(
                bounded_text(
                    "resolution_note",
                    resolution_note,
                    maximum=4096,
                    allow_empty=True,
                )
                if status is AgendaStatus.RESOLVED
                else ""
            ),
            metadata={
                **dict(item.metadata),
                **(
                    {
                        "completion_certificate_id": completion_certificate_id,
                        "completion_accepted": completion_accepted,
                    }
                    if completion_certificate_id is not None
                    else {}
                ),
            },
        )
        self._items[agenda_id] = updated
        payload = {
            "agenda_id": agenda_id,
            "previous_status": previous_status.value,
            "status": status.value,
            "attempt_count": attempts,
            "information_gain_bits": info,
            "cumulative_information_gain_bits": cumulative,
            "surprise_bits": surprise,
            "reopened": reopened,
            "completion_certificate_id": completion_certificate_id,
            "completion_accepted": completion_accepted,
            "item": updated.fingerprint,
        }
        return AttemptResult(
            agenda_id=agenda_id,
            previous_status=previous_status,
            status=status,
            attempt_count=attempts,
            information_gain_bits=info,
            cumulative_information_gain_bits=cumulative,
            surprise_bits=surprise,
            reopened=reopened,
            fingerprint=stable_fingerprint(payload),
        )

    def apply_completion_certificate(
        self,
        agenda_id: str,
        *,
        certificate_id: str,
        accepted: bool,
        resolution_note: str = "",
    ) -> AgendaItem:
        """Resolve an agenda item only from an explicit accepted certificate."""

        agenda_id = require_id("agenda_id", agenda_id)
        certificate_id = require_id("certificate_id", certificate_id)
        if not isinstance(accepted, bool):
            raise AgentContractError("accepted must be boolean")
        try:
            item = self._items[agenda_id]
        except KeyError as exc:
            raise AgentContractError("unknown agenda_id") from exc
        now = finite_number("now", self._clock())
        status = AgendaStatus.RESOLVED if accepted else AgendaStatus.QUEUED
        updated = replace(
            item,
            status=status,
            updated_at=now,
            defer_until=None,
            resolution_note=(
                bounded_text(
                    "resolution_note",
                    resolution_note,
                    maximum=4096,
                    allow_empty=True,
                )
                if accepted
                else ""
            ),
            metadata={
                **dict(item.metadata),
                "completion_certificate_id": certificate_id,
                "completion_accepted": accepted,
            },
        )
        self._items[agenda_id] = updated
        return updated

    def items_for_obligation(
        self,
        obligation_id: str,
    ) -> tuple[AgendaItem, ...]:
        obligation_id = require_id("obligation_id", obligation_id)
        return tuple(
            sorted(
                (
                    item
                    for item in self._items.values()
                    if item.obligation_id == obligation_id
                ),
                key=lambda item: item.agenda_id,
            )
        )

    def reopen_on_surprise(
        self,
        obligation_id: str,
        *,
        surprise_bits: float,
    ) -> tuple[AgendaItem, ...]:
        obligation_id = require_id("obligation_id", obligation_id)
        surprise = finite_number("surprise_bits", surprise_bits)
        if surprise < self.policy.reopen_surprise_bits:
            return ()
        now = finite_number("now", self._clock())
        reopened: list[AgendaItem] = []
        for agenda_id, item in tuple(self._items.items()):
            if item.obligation_id != obligation_id:
                continue
            if item.status is not AgendaStatus.RESOLVED:
                continue
            updated = replace(
                item,
                status=AgendaStatus.QUEUED,
                maximum_surprise_bits=max(item.maximum_surprise_bits, surprise),
                recurrence_count=item.recurrence_count + 1,
                updated_at=now,
                defer_until=None,
                resolution_note="",
            )
            self._items[agenda_id] = updated
            reopened.append(updated)
        return tuple(sorted(reopened, key=lambda item: item.agenda_id))

    def snapshot(self) -> AgendaSnapshot:
        items = tuple(sorted(self._items.values(), key=lambda item: item.agenda_id))
        ranked = self.rank()
        counts = {status: 0 for status in AgendaStatus}
        for item in items:
            counts[item.status] += 1
        unresolved_priority = sum(item.effective_priority for item in ranked)
        payload = {
            "items": [item.fingerprint for item in items],
            "ranked": [item.fingerprint for item in ranked],
            "counts": {status.value: counts[status] for status in AgendaStatus},
            "unresolved_priority": unresolved_priority,
        }
        return AgendaSnapshot(
            items=items,
            ranked=ranked,
            queued_count=counts[AgendaStatus.QUEUED],
            active_count=counts[AgendaStatus.ACTIVE],
            blocked_count=counts[AgendaStatus.BLOCKED],
            resolved_count=counts[AgendaStatus.RESOLVED],
            deferred_count=counts[AgendaStatus.DEFERRED],
            unresolved_priority=unresolved_priority,
            fingerprint=stable_fingerprint(payload),
        )

    def dump_state(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        return {
            "version": 1,
            "policy": {
                "recurrence_bonus": self.policy.recurrence_bonus,
                "attempt_bonus": self.policy.attempt_bonus,
                "age_bonus_per_day": self.policy.age_bonus_per_day,
                "maximum_age_bonus": self.policy.maximum_age_bonus,
                "resolution_information_gain_bits": self.policy.resolution_information_gain_bits,
                "reopen_surprise_bits": self.policy.reopen_surprise_bits,
                "maximum_items": self.policy.maximum_items,
                "maximum_attempts_before_defer": self.policy.maximum_attempts_before_defer,
                "require_assurance_for_resolution": self.policy.require_assurance_for_resolution,
            },
            "items": [item.as_json() for item in snapshot.items],
            "fingerprint": snapshot.fingerprint,
        }

    @classmethod
    def from_state(
        cls,
        state: Mapping[str, Any],
        *,
        clock: Callable[[], float] = time.time,
    ) -> "ResearchAgenda":
        payload = json_safe(dict(state))
        if payload.get("version") != 1:
            raise AgentContractError("unsupported research agenda state version")
        policy = ResearchAgendaPolicy(**dict(payload.get("policy", {})))
        agenda = cls(policy=policy, clock=clock)
        for raw in payload.get("items", []):
            value = dict(raw)
            item = AgendaItem(
                agenda_id=value["agenda_id"],
                obligation_id=value["obligation_id"],
                gap_id=value["gap_id"],
                gap_kind=GapKind(value["gap_kind"]),
                question=value["question"],
                base_priority=value["base_priority"],
                status=AgendaStatus(value["status"]),
                recurrence_count=value["recurrence_count"],
                attempt_count=value["attempt_count"],
                cumulative_information_gain_bits=value["cumulative_information_gain_bits"],
                maximum_surprise_bits=value["maximum_surprise_bits"],
                evidence_refs=tuple(value.get("evidence_refs", ())),
                dependencies=tuple(value.get("dependencies", ())),
                created_at=value["created_at"],
                updated_at=value["updated_at"],
                defer_until=value.get("defer_until"),
                last_probe_id=value.get("last_probe_id"),
                resolution_note=value.get("resolution_note", ""),
                metadata=dict(value.get("metadata", {})),
            )
            if item.agenda_id in agenda._items:
                raise AgentContractError("duplicate agenda_id in serialized state")
            agenda._items[item.agenda_id] = item
        agenda._trim()
        return agenda

    def item(self, agenda_id: str) -> AgendaItem:
        agenda_id = require_id("agenda_id", agenda_id)
        try:
            return self._items[agenda_id]
        except KeyError as exc:
            raise AgentContractError("unknown agenda_id") from exc

    def _trim(self) -> None:
        if len(self._items) <= self.policy.maximum_items:
            return
        # Keep unresolved work first, then most recently updated resolved items.
        ordered = sorted(
            self._items.values(),
            key=lambda item: (
                item.status is AgendaStatus.RESOLVED,
                -item.updated_at,
                item.agenda_id,
            ),
        )
        keep = {item.agenda_id for item in ordered[: self.policy.maximum_items]}
        self._items = {
            agenda_id: item
            for agenda_id, item in self._items.items()
            if agenda_id in keep
        }
