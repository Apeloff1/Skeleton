"""Deferred world mutations (command queues) applied at sync points.

Systems and scripts must not change world structure while queries iterate,
and conflict-free system batches must not observe each other's writes
mid-batch.  Both are solved by recording intent into a :class:`CommandQueue`
and applying it at the scheduler's sync point, in recording order.

``spawn`` returns a real handle immediately (reserved in the allocator) so
follow-up commands can reference the new entity before it exists.  A queue
that is discarded cancels its reservations; a cancelled handle can never be
confused with a later entity because its generation is retired.

Application policy is *validate-then-apply*: every command's component
values are normalised against the registry before any command runs (so a
malformed value rejects the whole queue with nothing applied).  Commands
whose target entity died in the meantime are skipped deterministically and
reported on the receipt rather than aborting everyone else's work.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .entities import handle_to_text
from .errors import CommandError, CommandOverflowError, ECSError
from .values import check_value, copy_value

if TYPE_CHECKING:  # pragma: no cover
    from .live import LiveWorld

MAX_QUEUE_COMMANDS = 1_000_000

SPAWN = "spawn"
DESPAWN = "despawn"
INSERT = "insert"
REMOVE = "remove"
PATCH = "patch"
SET_RESOURCE = "set_resource"
REMOVE_RESOURCE = "remove_resource"
SEND_EVENT = "send_event"
KINDS = (SPAWN, DESPAWN, INSERT, REMOVE, PATCH, SET_RESOURCE, REMOVE_RESOURCE, SEND_EVENT)


@dataclass(frozen=True)
class QueuedCommand:
    sequence: int
    kind: str
    entity: int | None = None
    name: str | None = None
    value: Any = None
    source: str = ""


@dataclass(frozen=True)
class SkippedCommand:
    sequence: int
    kind: str
    reason: str
    source: str = ""


@dataclass(frozen=True)
class ApplyReceipt:
    applied: int
    skipped: tuple[SkippedCommand, ...] = ()
    spawned: tuple[int, ...] = ()
    despawned: tuple[int, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.skipped


@dataclass
class CommandQueue:
    world: LiveWorld
    source: str = ""
    max_commands: int = MAX_QUEUE_COMMANDS
    _commands: list[QueuedCommand] = field(default_factory=list)
    _reserved: list[int] = field(default_factory=list)
    _closed: bool = False

    def __len__(self) -> int:
        return len(self._commands)

    def _push(self, kind: str, *, entity: int | None = None, name: str | None = None, value: Any = None) -> QueuedCommand:
        if self._closed:
            raise CommandError("command queue already applied or discarded")
        if len(self._commands) >= self.max_commands:
            raise CommandOverflowError("command queue full", context={"maximum": self.max_commands})
        cmd = QueuedCommand(len(self._commands), kind, entity, name, value, self.source)
        self._commands.append(cmd)
        return cmd

    # -- recording --------------------------------------------------------
    def spawn(self, components: Mapping[str, Any] | None = None) -> int:
        components = dict(components or {})
        for name, value in components.items():
            self.world.info(name)
            check_value(value, label=f"component {name}") if value is not None else None
        if self._closed:
            raise CommandError("command queue already applied or discarded")
        handle = self.world.entities.reserve()
        self._reserved.append(handle)
        self._push(SPAWN, entity=handle, value={k: copy_value(v) for k, v in components.items()})
        return handle

    def despawn(self, handle: int) -> None:
        self._push(DESPAWN, entity=handle)

    def insert(self, handle: int, name: str, value: Any = None) -> None:
        self.world.info(name)
        if value is not None:
            check_value(value, label=f"component {name}")
        self._push(INSERT, entity=handle, name=name, value=copy_value(value))

    def patch(self, handle: int, name: str, fields: Mapping[str, Any]) -> None:
        self.world.info(name)
        if not isinstance(fields, Mapping):
            raise CommandError("patch fields must be a mapping")
        fields = dict(fields)
        check_value(fields, label=f"patch {name}")
        self._push(PATCH, entity=handle, name=name, value=copy_value(fields))

    def remove(self, handle: int, name: str) -> None:
        self.world.info(name)
        self._push(REMOVE, entity=handle, name=name)

    def set_resource(self, name: str, value: Any) -> None:
        check_value(value, label=f"resource {name}")
        self._push(SET_RESOURCE, name=name, value=copy_value(value))

    def remove_resource(self, name: str) -> None:
        self._push(REMOVE_RESOURCE, name=name)

    def send(self, channel: str, payload: Any) -> None:
        check_value(payload, label=f"event {channel}")
        self._push(SEND_EVENT, name=channel, value=copy_value(payload))

    def extend(self, other: CommandQueue) -> None:
        """Move ``other``'s commands (and reservations) to the end of this queue."""
        if other.world is not self.world:
            raise CommandError("cannot merge queues of different worlds")
        if other._closed:
            raise CommandError("cannot merge a closed queue")
        for cmd in other._commands:
            self._push(cmd.kind, entity=cmd.entity, name=cmd.name, value=cmd.value)
        self._reserved.extend(other._reserved)
        other._commands = []
        other._reserved = []
        other._closed = True

    def commands(self) -> tuple[QueuedCommand, ...]:
        return tuple(self._commands)

    # -- lifecycle ----------------------------------------------------------
    def discard(self) -> None:
        if self._closed:
            return
        for handle in self._reserved:
            self.world.entities.cancel(handle)
        self._reserved = []
        self._commands = []
        self._closed = True

    def _validate(self) -> list[Any]:
        """Normalise every value up front; raise before anything is applied."""
        registry = self.world.components
        prepared: list[Any] = []
        for cmd in self._commands:
            try:
                if cmd.kind == SPAWN:
                    prepared.append({n: registry.normalise(n, v) for n, v in cmd.value.items()})
                elif cmd.kind == INSERT:
                    prepared.append(registry.normalise(cmd.name, cmd.value))
                else:
                    prepared.append(cmd.value)
            except ECSError as exc:
                raise CommandError(
                    "command queue rejected: invalid component value",
                    context={"sequence": cmd.sequence, "kind": cmd.kind, "name": cmd.name, "source": cmd.source, "error": str(exc)},
                ) from exc
        return prepared

    def apply(self) -> ApplyReceipt:
        if self._closed:
            raise CommandError("command queue already applied or discarded")
        world = self.world
        try:
            prepared = self._validate()
        except CommandError:
            self.discard()
            raise
        applied = 0
        skipped: list[SkippedCommand] = []
        spawned: list[int] = []
        despawned: list[int] = []
        committed: set[int] = set()
        try:
            for cmd, value in zip(self._commands, prepared):
                kind = cmd.kind
                if kind == SPAWN:
                    world._commit_reserved(cmd.entity, value)
                    committed.add(cmd.entity)
                    spawned.append(cmd.entity)
                elif kind in (DESPAWN, INSERT, REMOVE, PATCH):
                    if not world.is_alive(cmd.entity):
                        skipped.append(SkippedCommand(cmd.sequence, kind, f"entity {self._text(cmd.entity)} is not alive", cmd.source))
                        continue
                    if kind == DESPAWN:
                        world.despawn(cmd.entity)
                        despawned.append(cmd.entity)
                    elif kind == INSERT:
                        world._insert_normalised(cmd.entity, world.info(cmd.name), value)
                    elif kind == REMOVE:
                        if not world.has(cmd.entity, cmd.name):
                            skipped.append(SkippedCommand(cmd.sequence, kind, f"component {cmd.name} not present", cmd.source))
                            continue
                        world.remove(cmd.entity, cmd.name)
                    else:
                        if not world.has(cmd.entity, cmd.name):
                            skipped.append(SkippedCommand(cmd.sequence, kind, f"component {cmd.name} not present", cmd.source))
                            continue
                        world.patch(cmd.entity, cmd.name, value)
                elif kind == SET_RESOURCE:
                    world.set_resource(cmd.name, value)
                elif kind == REMOVE_RESOURCE:
                    if not world.has_resource(cmd.name):
                        skipped.append(SkippedCommand(cmd.sequence, kind, f"resource {cmd.name} not present", cmd.source))
                        continue
                    world.remove_resource(cmd.name)
                elif kind == SEND_EVENT:
                    world.send(cmd.name, value)
                else:  # pragma: no cover - guarded by KINDS
                    raise CommandError("unknown command kind", context={"kind": kind})
                applied += 1
        finally:
            # Reservations whose spawn never ran (error mid-apply) are returned.
            for handle in self._reserved:
                if handle not in committed:
                    world.entities.cancel(handle)
            self._reserved = []
            self._commands = []
            self._closed = True
        return ApplyReceipt(applied, tuple(skipped), tuple(spawned), tuple(despawned))

    @staticmethod
    def _text(handle: Any) -> str:
        try:
            return handle_to_text(handle)
        except ECSError:
            return repr(handle)


__all__ = ["KINDS", "ApplyReceipt", "CommandQueue", "QueuedCommand", "SkippedCommand"]
