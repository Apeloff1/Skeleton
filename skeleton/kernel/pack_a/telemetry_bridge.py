"""telemetry_bridge — emit Pack A meter snapshots into kernel EventBus shapes."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from skeleton.kernel.pack_a.metrics import InfraMeter, MeterSnapshot, default_meter


class TelemetryBridge:
    """Adapt InfraMeter snapshots to a simple event list (no bus coupling required)."""

    def __init__(self, meter: Optional[InfraMeter] = None) -> None:
        self.meter = meter if meter is not None else default_meter()
        self._events: List[Dict[str, Any]] = []

    def publish_snapshot(self) -> Dict[str, Any]:
        snap = self.meter.snapshot()
        event = {
            "type": "pack_a.meter_snapshot",
            "when": time.time(),
            "payload": snap.as_dict(),
        }
        self._events.append(event)
        if len(self._events) > 1024:
            del self._events[0 : len(self._events) - 1024]
        return event

    def recent(self, limit: int = 32) -> List[Dict[str, Any]]:
        return list(self._events[-limit:])


def snapshot_event(meter: Optional[InfraMeter] = None) -> Dict[str, Any]:
    return TelemetryBridge(meter).publish_snapshot()


__all__ = ["TelemetryBridge", "snapshot_event"]
