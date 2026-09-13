"""Small bounded ownership registry for runtime reservations."""

from .gameforge_reservation import Reservation


class ReservationBook:
    def __init__(self, capacity: int):
        if not isinstance(capacity, int) or capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._items = {}
        self._sequence = 0

    def add(self, request_id: str):
        if not request_id:
            raise ValueError("request_id is required")
        existing = self._items.get(request_id)
        if existing is not None:
            return existing
        if len(self._items) >= self.capacity:
            return None
        reservation = Reservation(request_id, self._sequence)
        self._sequence += 1
        self._items[request_id] = reservation
        return reservation

    def remove(self, request_id: str):
        return self._items.pop(request_id, None)

    def contains(self, request_id: str) -> bool:
        return request_id in self._items

    def get(self, request_id: str):
        return self._items.get(request_id)

    def __len__(self):
        return len(self._items)

    @property
    def remaining(self):
        return self.capacity - len(self._items)

    @property
    def full(self):
        return len(self._items) >= self.capacity
