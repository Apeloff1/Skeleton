"""Monotonic runtime timing and unforgeable walltime conversion."""
from __future__ import annotations
import time
from datetime import datetime, timezone
from .canonical import integer
from .errors import deny


def mono_ns() -> int:
    return time.monotonic_ns()


def elapsed_ms(start_ns: int, finish_ns: int) -> int:
    integer(start_ns, "start-monotonic", 0, 2**63 - 1)
    integer(finish_ns, "finish-monotonic", 0, 2**63 - 1)
    if finish_ns < start_ns:
        deny("clock-regression")
    return (finish_ns - start_ns) // 1000000


def utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
