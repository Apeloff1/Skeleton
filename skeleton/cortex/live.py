"""
Skeleton Cortex — Live serving organism singleton

The genesis handle is the inspectable twin; this module holds the
process-lived JeevesCortex that serving surfaces (API, cockpit)
observe and control at runtime.
"""

from __future__ import annotations

from typing import Any, Optional

from skeleton.cortex.neocortex import ControlSurface, JeevesCortex
from skeleton.kernel.events import EventBus

_live_cortex: Optional[JeevesCortex] = None
_live_control: Optional[ControlSurface] = None


def get_live(bus: Optional[EventBus] = None) -> JeevesCortex:
    """Get or create the process-lived cortex singleton."""
    global _live_cortex, _live_control
    if _live_cortex is None:
        _live_cortex = JeevesCortex(bus=bus or EventBus())
        _live_control = ControlSurface(_live_cortex, bus=bus)
    return _live_cortex


def get_control() -> Optional[ControlSurface]:
    """Control surface bound to the live cortex, if initialized."""
    return _live_control


def attach(bus: EventBus) -> JeevesCortex:
    """Attach the live cortex to a bus (idempotent)."""
    cortex = get_live(bus)
    cortex._bus = bus
    bus.subscribe("*", cortex._on_event)
    return cortex


def status() -> dict[str, Any]:
    """Snapshot of the live organism for /cortex/status surfaces."""
    if _live_cortex is None:
        return {"live": False, "events_captured": 0}
    stats = _live_cortex.stats()
    stats["live"] = True
    return stats
