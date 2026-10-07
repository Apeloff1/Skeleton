from dataclasses import dataclass


def _int(value: object, *, positive: bool = False, nonnegative: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("integer value required")
    if positive and value <= 0:
        raise ValueError("positive integer required")
    if nonnegative and value < 0:
        raise ValueError("nonnegative integer required")
    return value


def _align_up(value: int, alignment: int) -> int:
    return ((value + alignment - 1) // alignment) * alignment


@dataclass(frozen=True)
class GPUMemoryReservation:
    reservation_id: str
    start: int
    size: int
    owner: str = ""
    purpose: str = ""

    def __post_init__(self) -> None:
        if not self.reservation_id:
            raise ValueError("reservation identity required")
        _int(self.start, nonnegative=True)
        _int(self.size, positive=True)

    @property
    def end(self) -> int:
        return self.start + self.size


@dataclass(frozen=True)
class GPUAllocation:
    reservation: GPUMemoryReservation
    committed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.reservation, GPUMemoryReservation):
            raise ValueError("reservation required")
        if not isinstance(self.committed, bool):
            raise ValueError("committed must be boolean")


@dataclass(frozen=True)
class GPUMemoryPool:
    capacity: int
    reservations: tuple[GPUMemoryReservation, ...] = ()

    def __post_init__(self) -> None:
        _int(self.capacity, positive=True)
        if any(not isinstance(r, GPUMemoryReservation) for r in self.reservations):
            raise ValueError("invalid GPU reservation")
        ids = [r.reservation_id for r in self.reservations]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate reservation identity")
        used = sorted(self.reservations, key=lambda item: (item.start, item.reservation_id))
        if any(a.end > b.start for a, b in zip(used, used[1:])):
            raise ValueError("overlapping GPU reservations")
        if any(r.end > self.capacity for r in used):
            raise ValueError("out-of-bounds GPU reservation")

    @property
    def used(self) -> int:
        return sum(r.size for r in self.reservations)

    @property
    def free(self) -> int:
        return self.capacity - self.used

    @property
    def largest_free_block(self) -> int:
        used = sorted(self.reservations, key=lambda item: item.start)
        cursor = 0
        largest = 0
        for reservation in used:
            largest = max(largest, reservation.start - cursor)
            cursor = reservation.end
        return max(largest, self.capacity - cursor)

    @property
    def fragmentation_bytes(self) -> int:
        return self.free - self.largest_free_block

    def reserve(
        self,
        rid: str,
        size: int,
        *,
        alignment: int = 1,
        owner: str = "",
        purpose: str = "",
    ) -> tuple["GPUMemoryPool", GPUMemoryReservation]:
        if not rid or rid in {r.reservation_id for r in self.reservations}:
            raise ValueError("unique reservation id required")
        _int(size, positive=True)
        _int(alignment, positive=True)

        used = sorted(self.reservations, key=lambda item: item.start)
        cursor = 0
        start: int | None = None
        for reservation in used:
            candidate = _align_up(cursor, alignment)
            if candidate + size <= reservation.start:
                start = candidate
                break
            cursor = max(cursor, reservation.end)
        if start is None:
            start = _align_up(cursor, alignment)
        if start + size > self.capacity:
            raise MemoryError("gpu memory unavailable")

        reservation = GPUMemoryReservation(rid, start, size, owner, purpose)
        return GPUMemoryPool(self.capacity, self.reservations + (reservation,)), reservation

    def release(self, rid: str) -> "GPUMemoryPool":
        if rid not in {r.reservation_id for r in self.reservations}:
            raise KeyError("unknown reservation")
        return GPUMemoryPool(
            self.capacity,
            tuple(r for r in self.reservations if r.reservation_id != rid),
        )

    def allocation(self, rid: str, *, committed: bool = True) -> GPUAllocation:
        if not isinstance(committed, bool):
            raise ValueError("committed must be boolean")
        reservation = next(
            (r for r in self.reservations if r.reservation_id == rid),
            None,
        )
        if reservation is None:
            raise KeyError("unknown reservation")
        return GPUAllocation(reservation, committed)
