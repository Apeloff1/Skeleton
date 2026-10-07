"""Generational runtime entity handles for the live (dense) ECS world.

The authoritative :class:`~.store.EntityStore` identifies entities with
human-readable digest-suffixed strings.  That is ideal for evidence and
diffing but too heavy for a per-tick game loop, so the live world uses packed
integer handles instead::

    handle = (generation << INDEX_BITS) | index

``index`` is a dense slot number that is recycled after despawn and
``generation`` is bumped on every recycle, so a stale handle held by a script
or a system can never alias the entity that later reuses its slot (the
classic ABA problem).  Free slots are recycled FIFO rather than LIFO: FIFO
spreads generation growth across slots and is equally deterministic.

Every handle has a stable textual form (:func:`handle_to_text`) that is a
valid :func:`~.identity.validate_entity_id` string, which is how the live
world bridges into ``EntityStore`` records, inspection and world sessions.
"""
from __future__ import annotations

import re
from collections import deque
from collections.abc import Iterator, Mapping
from typing import Any

from .errors import BoundsError, EntityHandleError

INDEX_BITS = 32
INDEX_MASK = (1 << INDEX_BITS) - 1
MAX_GENERATION = (1 << 31) - 1
MAX_LIVE_ENTITIES = 1_000_000
HANDLE_TEXT_PREFIX = "live"
_TEXT_RE = re.compile(r"^live:e([0-9a-f]{8})g([0-9a-f]{1,8})$")

# Slot states.  RESERVED slots were handed out by a deferred command queue and
# become ALIVE when the queue is applied, or FREE again if it is discarded.
FREE = 0
ALIVE = 1
RESERVED = 2


def pack_handle(index: int, generation: int) -> int:
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= INDEX_MASK:
        raise EntityHandleError("entity index out of range", context={"index": index})
    if isinstance(generation, bool) or not isinstance(generation, int) or not 0 <= generation <= MAX_GENERATION:
        raise EntityHandleError("entity generation out of range", context={"generation": generation})
    return (generation << INDEX_BITS) | index


def handle_index(handle: int) -> int:
    return handle & INDEX_MASK


def handle_generation(handle: int) -> int:
    return handle >> INDEX_BITS


def check_handle(handle: Any) -> int:
    """Return ``handle`` if it is structurally a valid packed handle."""
    if isinstance(handle, bool) or not isinstance(handle, int) or handle < 0:
        raise EntityHandleError("entity handle must be a non-negative integer", context={"handle": handle})
    if handle_generation(handle) > MAX_GENERATION:
        raise EntityHandleError("entity handle generation out of range", context={"handle": handle})
    return handle


def handle_to_text(handle: int) -> str:
    check_handle(handle)
    return f"{HANDLE_TEXT_PREFIX}:e{handle_index(handle):08x}g{handle_generation(handle):x}"


def handle_from_text(text: str) -> int:
    if not isinstance(text, str):
        raise EntityHandleError("entity handle text must be a string")
    match = _TEXT_RE.fullmatch(text)
    if match is None:
        raise EntityHandleError("malformed entity handle text", context={"text": text[:80]})
    return pack_handle(int(match.group(1), 16), int(match.group(2), 16))


class HandleAllocator:
    """Deterministic generational slot allocator.

    The allocator is pure state: identical call sequences always produce
    identical handles, and :meth:`snapshot` / :meth:`restore` round-trip the
    complete state (generations, slot states and the free-queue order) so a
    restored world keeps allocating exactly as the original would have.
    """

    __slots__ = ("_alive", "_free", "_generations", "_states", "capacity")

    def __init__(self, capacity: int = MAX_LIVE_ENTITIES) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int) or not 1 <= capacity <= INDEX_MASK + 1:
            raise BoundsError("allocator capacity out of range", context={"capacity": capacity})
        self.capacity = capacity
        self._generations: list[int] = []
        self._states: bytearray = bytearray()
        self._free: deque[int] = deque()
        self._alive = 0

    # -- queries ---------------------------------------------------------
    def __len__(self) -> int:
        return self._alive

    @property
    def alive_count(self) -> int:
        return self._alive

    @property
    def slot_count(self) -> int:
        return len(self._generations)

    def current(self, index: int) -> int:
        """Return the handle currently occupying ``index`` (alive or not)."""
        if not 0 <= index < len(self._generations):
            raise EntityHandleError("entity index was never allocated", context={"index": index})
        return pack_handle(index, self._generations[index])

    def state_of(self, handle: int) -> int:
        check_handle(handle)
        index = handle_index(handle)
        if index >= len(self._generations) or self._generations[index] != handle_generation(handle):
            return FREE
        return self._states[index]

    def is_alive(self, handle: Any) -> bool:
        if isinstance(handle, bool) or not isinstance(handle, int) or handle < 0:
            return False
        index = handle & INDEX_MASK
        return (
            index < len(self._generations)
            and self._generations[index] == handle >> INDEX_BITS
            and self._states[index] == ALIVE
        )

    def require_alive(self, handle: Any) -> int:
        if not self.is_alive(handle):
            check_handle(handle)
            raise EntityHandleError("entity is not alive", context={"entity": handle_to_text(handle)})
        return handle

    def alive_handles(self) -> Iterator[int]:
        """Alive handles in ascending slot order (layout independent)."""
        generations = self._generations
        for index, state in enumerate(self._states):
            if state == ALIVE:
                yield (generations[index] << INDEX_BITS) | index

    # -- mutation --------------------------------------------------------
    def _take_slot(self) -> int:
        if self._free:
            return self._free.popleft()
        if len(self._generations) >= self.capacity:
            raise BoundsError("live entity capacity exhausted", context={"capacity": self.capacity})
        self._generations.append(0)
        self._states.append(FREE)
        return len(self._generations) - 1

    def allocate(self) -> int:
        index = self._take_slot()
        self._states[index] = ALIVE
        self._alive += 1
        return pack_handle(index, self._generations[index])

    def reserve(self) -> int:
        """Hand out a handle that is not alive until :meth:`commit`."""
        index = self._take_slot()
        self._states[index] = RESERVED
        return pack_handle(index, self._generations[index])

    def commit(self, handle: int) -> int:
        if self.state_of(handle) != RESERVED:
            raise EntityHandleError("handle is not reserved", context={"entity": handle_to_text(handle)})
        self._states[handle_index(handle)] = ALIVE
        self._alive += 1
        return handle

    def cancel(self, handle: int) -> None:
        """Return a reserved-but-never-committed handle to the free queue.

        The generation is still bumped so the cancelled handle can never be
        confused with a later occupant of the same slot.
        """
        if self.state_of(handle) != RESERVED:
            raise EntityHandleError("handle is not reserved", context={"entity": handle_to_text(handle)})
        self._recycle(handle_index(handle))

    def release(self, handle: int) -> None:
        self.require_alive(handle)
        self._alive -= 1
        self._recycle(handle_index(handle))

    def _recycle(self, index: int) -> None:
        generation = self._generations[index] + 1
        self._states[index] = FREE
        if generation > MAX_GENERATION:
            # Retire the slot permanently rather than wrap and risk aliasing.
            self._generations[index] = MAX_GENERATION
            return
        self._generations[index] = generation
        self._free.append(index)

    # -- persistence -----------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return {
            "capacity": self.capacity,
            "generations": list(self._generations),
            "states": list(self._states),
            "free": list(self._free),
        }

    @classmethod
    def restore(cls, record: Mapping[str, Any]) -> HandleAllocator:
        if not isinstance(record, Mapping) or set(record) != {"capacity", "generations", "states", "free"}:
            raise EntityHandleError("allocator record fields mismatch")
        allocator = cls(record["capacity"])
        generations = list(record["generations"])
        states = list(record["states"])
        free = list(record["free"])
        if len(generations) != len(states) or len(generations) > allocator.capacity:
            raise EntityHandleError("allocator record is inconsistent")
        for value in generations:
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_GENERATION:
                raise EntityHandleError("allocator record has invalid generation")
        for value in states:
            if value not in (FREE, ALIVE, RESERVED):
                raise EntityHandleError("allocator record has invalid slot state")
        if RESERVED in states:
            raise EntityHandleError("allocator snapshot must not contain reserved slots")
        if len(set(free)) != len(free) or any(
            not isinstance(i, int) or not 0 <= i < len(states) or states[i] != FREE for i in free
        ):
            raise EntityHandleError("allocator free queue is inconsistent")
        allocator._generations = generations
        allocator._states = bytearray(states)
        allocator._free = deque(free)
        allocator._alive = sum(1 for state in states if state == ALIVE)
        return allocator


__all__ = [
    "ALIVE",
    "FREE",
    "HANDLE_TEXT_PREFIX",
    "INDEX_BITS",
    "MAX_GENERATION",
    "MAX_LIVE_ENTITIES",
    "RESERVED",
    "HandleAllocator",
    "check_handle",
    "handle_from_text",
    "handle_generation",
    "handle_index",
    "handle_to_text",
    "pack_handle",
]
