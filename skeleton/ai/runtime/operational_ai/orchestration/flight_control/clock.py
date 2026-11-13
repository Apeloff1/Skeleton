"""Machine boot identity fences monotonic leases across OS restarts."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re,time
from .contracts import FlightError

_BOOT=re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


@dataclass(frozen=True,slots=True)
class ClockStamp:
    boot:str
    tick:int
    wall:int


class BootClock:
    """Production source: kernel boot ID + monotonic time + wall timestamp.

    Never compare monotonic ticks from different boot IDs. If boot identity
    becomes unreadable, block scheduling rather than fabricating a lease.
    """
    def __init__(self, path:str|Path='/proc/sys/kernel/random/boot_id'):
        self._path=Path(path)

    def stamp(self)->ClockStamp:
        try:
            boot=self._path.read_text(encoding='ascii').strip().lower()
        except (OSError,UnicodeError) as exc:
            raise FlightError('kernel boot identity unavailable') from exc
        if not _BOOT.fullmatch(boot):raise FlightError('invalid kernel boot identity')
        return ClockStamp(boot,time.monotonic_ns(),time.time_ns())
