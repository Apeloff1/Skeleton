"""Monotonic, bounded in-process replay cursor; not durable acknowledgement."""
from threading import RLock

MAX_REPLAY_BATCH = 65_536
MAX_SEQUENCE = (1 << 63) - 1


class ReplayCursor:
    def __init__(self, checkpoint=-1):
        if type(checkpoint) is not int or not -1 <= checkpoint <= MAX_SEQUENCE:
            raise ValueError("invalid replay checkpoint")
        self._checkpoint = checkpoint
        self._lock = RLock()

    @property
    def checkpoint(self):
        with self._lock:
            return self._checkpoint

    def consume(self, events):
        """Reject malformed or gapped batches atomically; ignore old prefixes."""
        with self._lock:
            fresh = []
            previous = -1
            for index, event in enumerate(events):
                if index >= MAX_REPLAY_BATCH:
                    raise ValueError("replay batch budget exceeded")
                seq = event.sequence
                if type(seq) is not int or not 0 <= seq <= MAX_SEQUENCE or seq <= previous:
                    raise ValueError("replay events must have strictly increasing sequences")
                previous = seq
                if seq <= self._checkpoint:
                    continue
                if seq != self._checkpoint + len(fresh) + 1:
                    raise ValueError("replay sequence gap; reconcile before advancing")
                fresh.append(event)
            if fresh:
                self._checkpoint = fresh[-1].sequence
            return tuple(fresh)
