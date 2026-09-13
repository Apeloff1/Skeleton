"""Priority queue primitive for ordered repair execution."""

import heapq


class RepairQueue:
    def __init__(self) -> None:
        self._items = []
        self._sequence = 0

    def push(self, priority: int, name: str) -> None:
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("priority must be an integer")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        heapq.heappush(self._items, (-priority, self._sequence, name))
        self._sequence += 1

    def pop(self):
        if not self._items:
            return None
        _, _, name = heapq.heappop(self._items)
        return name

    def __len__(self) -> int:
        return len(self._items)

    @property
    def empty(self) -> bool:
        return not self._items
