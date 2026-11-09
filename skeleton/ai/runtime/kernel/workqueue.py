"""Backward-compatible alias — ``skeleton.kernel.workqueue`` re-exports
the weighted-fair DRR work queue from ``work_queue``.

This shim exists so consumers importing ``FairWorkQueue``, ``QueueFullError``,
or ``WorkItem`` from either ``skeleton.kernel`` or ``skeleton.kernel.workqueue``
get the same implementation regardless of which entry-point they use.
"""

from __future__ import annotations

from .work_queue import LaneFullError as QueueFullError
from .work_queue import WorkItem
from .work_queue import WorkQueue as FairWorkQueue

__all__ = ["FairWorkQueue", "QueueFullError", "WorkItem"]
