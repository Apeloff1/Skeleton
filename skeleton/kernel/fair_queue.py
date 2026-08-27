"""Backward-compatible alias — ``skeleton.kernel.fair_queue`` re-exports
the deficit-round-robin lane queue from ``work_queue``.

A second, orphan queue implementation (priority heap, per-submitter
virtual finish, deadline expiry) lived here with no importers. It has
been folded into ``work_queue.py`` so the kernel carries one queue
core: weighted-fair DRR lanes with explicit capacity bounds.

Names are mapped to keep this module import-compatible: the old
``FairWorkQueue``/``QueueError``/``QueueFullError``/``WorkItem`` all
resolve onto the canonical ``work_queue`` implementation, matching the
existing ``workqueue`` shim.
"""

from __future__ import annotations

from .work_queue import LaneFullError as QueueFullError
from .work_queue import WorkItem
from .work_queue import WorkQueue as FairWorkQueue
from .work_queue import WorkQueueError as QueueError

__all__ = ["FairWorkQueue", "QueueError", "QueueFullError", "WorkItem"]
