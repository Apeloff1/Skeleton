"""Bounded, synchronized process-local reservation ownership."""
from threading import RLock

from .gameforge_reservation import Reservation

MAX_RESERVATIONS = 65_536


class ReservationBook:
    def __init__(self, capacity: int):
        if type(capacity) is not int or not 1 <= capacity <= MAX_RESERVATIONS:
            raise ValueError("bounded positive capacity required")
        self._capacity = capacity
        self._items = {}
        self._sequence = 0
        self._lock = RLock()

    @staticmethod
    def _identity(request_id):
        if type(request_id) is not str or not request_id.strip() or len(request_id) > 1024:
            raise ValueError("bounded request identity required")

    @property
    def capacity(self):
        return self._capacity

    def add(self, request_id: str):
        self._identity(request_id)
        with self._lock:
            existing = self._items.get(request_id)
            if existing is not None:
                return existing
            if len(self._items) >= self._capacity:
                return None
            if self._sequence >= (1 << 63) - 1:
                raise RuntimeError("reservation sequence exhausted")
            reservation = Reservation(request_id, self._sequence)
            self._sequence += 1
            self._items[request_id] = reservation
            return reservation

    def remove(self, request_id: str):
        self._identity(request_id)
        with self._lock:
            return self._items.pop(request_id, None)

    def remove_exact(self, request_id: str, sequence: int):
        """Reject a stale release after the same request has been re-admitted."""
        self._identity(request_id)
        if type(sequence) is not int or sequence < 0:
            raise ValueError("invalid reservation generation")
        with self._lock:
            item = self._items.get(request_id)
            if item is None or item.sequence != sequence:
                return None
            return self._items.pop(request_id)

    def contains(self, request_id: str) -> bool:
        return self.get(request_id) is not None

    def get(self, request_id: str):
        self._identity(request_id)
        with self._lock:
            return self._items.get(request_id)

    def __len__(self):
        with self._lock:
            return len(self._items)

    @property
    def remaining(self):
        return self._capacity - len(self)

    @property
    def full(self):
        return len(self) >= self._capacity
