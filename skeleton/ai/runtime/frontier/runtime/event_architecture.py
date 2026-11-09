"""Version compatibility and replay-retention contracts for event architecture.

These contracts sit above the transport-neutral stream envelope. They provide:
- explicit per-event schema compatibility authority,
- deterministic upgrade-path validation,
- replay-safe retention planning that never compacts beyond acknowledged history.

They deliberately do not grant migration or compaction authority by themselves.
Storage backends must apply decisions transactionally.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable

from skeleton.frontier.runtime.operation_stream import StreamContractError


MAX_SCHEMA_VERSIONS = 256
MAX_SCHEMA_UPGRADE_EDGES = 2048
MAX_EVENT_CONTRACT_DECLARATIONS = 4096


class EventCompatibilityError(StreamContractError):
    """Event schema compatibility or retention policy is invalid."""


def _version(value: object, field: str) -> int:
    if type(value) is not int or not 1 <= value <= 2**31 - 1:
        raise EventCompatibilityError(f"{field} must be a bounded positive integer")
    return value


def _event_type(value: object) -> str:
    if (type(value) is not str or not value or value != value.strip() or
            any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise EventCompatibilityError("event_type must be canonical non-empty text")
    if len(value) > 128:
        raise EventCompatibilityError("event_type exceeds maximum length")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise EventCompatibilityError("event_type must be valid UTF-8") from exc
    return value


def _versions(values: Iterable[int], field: str) -> tuple[int, ...]:
    if isinstance(values, (str, bytes)):
        raise EventCompatibilityError(f"{field} must be an iterable of versions")
    unique: set[int] = set()
    try:
        for count, value in enumerate(values, start=1):
            if count > MAX_SCHEMA_VERSIONS:
                raise EventCompatibilityError(f"{field} exceeds version count limit")
            unique.add(_version(value, field))
    except TypeError as exc:
        raise EventCompatibilityError(f"{field} must be iterable") from exc
    if not unique:
        raise EventCompatibilityError(f"{field} must not be empty")
    return tuple(sorted(unique))


@dataclass(frozen=True, slots=True)
class EventSchemaContract:
    """Compatibility authority for one logical event type."""

    event_type: str
    current_version: int
    readable_versions: tuple[int, ...]
    writable_versions: tuple[int, ...]
    upgrade_edges: tuple[tuple[int, int], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_type", _event_type(self.event_type))
        current = _version(self.current_version, "current_version")
        readable = _versions(self.readable_versions, "readable_versions")
        writable = _versions(self.writable_versions, "writable_versions")
        if current not in readable:
            raise EventCompatibilityError("current_version must be readable")
        if current not in writable:
            raise EventCompatibilityError("current_version must be writable")

        edges: set[tuple[int, int]] = set()
        try:
            for count, raw in enumerate(self.upgrade_edges, start=1):
                if count > MAX_SCHEMA_UPGRADE_EDGES:
                    raise EventCompatibilityError("upgrade_edges exceeds bounded edge limit")
                if not isinstance(raw, tuple) or len(raw) != 2:
                    raise EventCompatibilityError("upgrade_edges must contain version pairs")
                source = _version(raw[0], "upgrade source")
                target = _version(raw[1], "upgrade target")
                if source == target:
                    raise EventCompatibilityError("upgrade edge must change version")
                if source not in readable or target not in readable:
                    raise EventCompatibilityError("upgrade edge versions must be readable")
                if target < source:
                    raise EventCompatibilityError("upgrade edges must be monotonic")
                edges.add((source, target))
        except TypeError as exc:
            raise EventCompatibilityError("upgrade_edges must be iterable") from exc

        object.__setattr__(self, "current_version", current)
        object.__setattr__(self, "readable_versions", readable)
        object.__setattr__(self, "writable_versions", writable)
        object.__setattr__(self, "upgrade_edges", tuple(sorted(edges)))

        for version in readable:
            if version != current:
                self.upgrade_path(version)

    def assert_readable(self, version: int) -> None:
        version = _version(version, "schema version")
        if version not in self.readable_versions:
            raise EventCompatibilityError(
                f"{self.event_type} schema v{version} is not readable"
            )

    def assert_writable(self, version: int) -> None:
        version = _version(version, "schema version")
        if version not in self.writable_versions:
            raise EventCompatibilityError(
                f"{self.event_type} schema v{version} is not writable"
            )

    def upgrade_path(self, version: int) -> tuple[int, ...]:
        """Return a deterministic path from version to current_version."""

        start = _version(version, "schema version")
        self.assert_readable(start)
        if start == self.current_version:
            return (start,)

        adjacency: dict[int, list[int]] = {}
        for source, target in self.upgrade_edges:
            adjacency.setdefault(source, []).append(target)
        for targets in adjacency.values():
            targets.sort()

        queue: deque[tuple[int, tuple[int, ...]]] = deque([(start, (start,))])
        visited = {start}
        while queue:
            node, path = queue.popleft()
            for target in adjacency.get(node, ()):
                if target == self.current_version:
                    return path + (target,)
                if target not in visited:
                    visited.add(target)
                    queue.append((target, path + (target,)))

        raise EventCompatibilityError(
            f"{self.event_type} schema v{start} has no upgrade path to "
            f"v{self.current_version}"
        )


class EventCompatibilityRegistry:
    """Immutable-by-identity registry of event schema contracts."""

    def __init__(self, contracts: Iterable[EventSchemaContract] = ()) -> None:
        self._contracts: dict[str, EventSchemaContract] = {}
        try:
            for count, contract in enumerate(contracts, start=1):
                if count > MAX_EVENT_CONTRACT_DECLARATIONS:
                    raise EventCompatibilityError("event contract declaration budget exceeded")
                self.register(contract)
        except TypeError as exc:
            raise EventCompatibilityError("event contract declarations must be iterable") from exc

    def register(self, contract: EventSchemaContract) -> None:
        if not isinstance(contract, EventSchemaContract):
            raise EventCompatibilityError("contract must be EventSchemaContract")
        prior = self._contracts.get(contract.event_type)
        if prior is None and len(self._contracts) >= MAX_EVENT_CONTRACT_DECLARATIONS:
            raise EventCompatibilityError("event contract registry at capacity")
        if prior is not None and prior != contract:
            raise EventCompatibilityError(
                f"event_type {contract.event_type!r} already has a different contract"
            )
        self._contracts[contract.event_type] = contract

    def contract(self, event_type: str) -> EventSchemaContract:
        key = _event_type(event_type)
        try:
            return self._contracts[key]
        except KeyError as exc:
            raise EventCompatibilityError(
                f"event_type {key!r} is not registered"
            ) from exc

    def assert_readable(self, event_type: str, version: int) -> None:
        self.contract(event_type).assert_readable(version)

    def assert_writable(self, event_type: str, version: int) -> None:
        self.contract(event_type).assert_writable(version)

    def upgrade_path(self, event_type: str, version: int) -> tuple[int, ...]:
        return self.contract(event_type).upgrade_path(version)

    @property
    def event_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._contracts))


@dataclass(frozen=True, slots=True)
class RetentionDecision:
    """Deterministic compaction target and resulting replay floor."""

    compact_through: int
    replay_floor: int
    retained_events: int

    def __post_init__(self) -> None:
        for field in ("compact_through", "replay_floor", "retained_events"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise EventCompatibilityError(f"{field} must be a non-negative integer")
        if self.replay_floor != self.compact_through + 1:
            raise EventCompatibilityError(
                "replay_floor must immediately follow compact_through"
            )


@dataclass(frozen=True, slots=True)
class EventRetentionPolicy:
    """Replay-safe tail-retention policy."""

    minimum_retained_events: int = 1
    terminal_minimum_retained_events: int = 1

    def __post_init__(self) -> None:
        for field in ("minimum_retained_events", "terminal_minimum_retained_events"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise EventCompatibilityError(
                    f"{field} must be a non-negative integer"
                )

    def plan(
        self,
        *,
        compacted_through: int,
        latest_sequence: int,
        acknowledged_through: int | None,
        terminal: bool,
    ) -> RetentionDecision:
        current = self._sequence(compacted_through, "compacted_through")
        latest = self._sequence(latest_sequence, "latest_sequence")
        if latest < current:
            raise EventCompatibilityError(
                "latest_sequence must not precede compacted_through"
            )
        if not isinstance(terminal, bool):
            raise EventCompatibilityError("terminal must be bool")

        if acknowledged_through is None:
            target = current
        else:
            acknowledged = self._sequence(
                acknowledged_through, "acknowledged_through"
            )
            if acknowledged > latest:
                raise EventCompatibilityError(
                    "acknowledged_through exceeds latest_sequence"
                )
            keep = (
                self.terminal_minimum_retained_events
                if terminal
                else self.minimum_retained_events
            )
            tail_bound = max(current, latest - keep)
            target = max(current, min(acknowledged, tail_bound))

        retained = latest - target
        return RetentionDecision(
            compact_through=target,
            replay_floor=target + 1,
            retained_events=retained,
        )

    @staticmethod
    def _sequence(value: object, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise EventCompatibilityError(
                f"{field} must be a non-negative integer"
            )
        return value


__all__ = [
    "MAX_SCHEMA_VERSIONS",
    "MAX_SCHEMA_UPGRADE_EDGES",
    "MAX_EVENT_CONTRACT_DECLARATIONS",
    "EventCompatibilityError",
    "EventCompatibilityRegistry",
    "EventRetentionPolicy",
    "EventSchemaContract",
    "RetentionDecision",
]
