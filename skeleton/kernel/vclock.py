"""Backward-compatible alias — ``skeleton.kernel.vclock`` re-exports the
canonical immutable vector-clock implementation from ``clocks``.

The duplicate mutable ``VectorClock`` that lived here has been folded
into ``clocks.py`` so the kernel carries exactly one vector-clock
implementation, plus the ``ClockRegistry`` and ``order_events`` helpers
new vclock importers can use directly.
"""

from __future__ import annotations

from .clocks import ClockError, ClockRegistry, VectorClock, order_events

__all__ = ["ClockError", "ClockRegistry", "VectorClock", "order_events"]
