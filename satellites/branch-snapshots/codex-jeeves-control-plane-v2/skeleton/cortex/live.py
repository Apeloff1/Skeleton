"""Process-lived cortex + Jeeves singletons.

Serving surfaces (API, cockpit, CLI plan) share one organism. Tests stay
hermetic via GameForgeRun() (not live) or reset_live().
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Optional

from skeleton.cortex.neocortex import ControlSurface, JeevesCortex
from skeleton.kernel.events import EventBus

_LOCK = threading.RLock()
_live_cortex: Optional[JeevesCortex] = None
_live_control: Optional[ControlSurface] = None
_JEEVES = None


def own_path() -> Path:
    raw = os.environ.get("SKELETON_OWN")
    if raw:
        return Path(raw)
    return Path(".skeleton") / "own.json"


def get_live(bus: Optional[EventBus] = None) -> JeevesCortex:
    """Get or create the process-lived cortex singleton (API wiring name)."""
    global _live_cortex, _live_control
    with _LOCK:
        if _live_cortex is None:
            _live_cortex = JeevesCortex(bus=bus or EventBus())
            _live_control = ControlSurface(_live_cortex, bus=bus)
            path = own_path()
            if path.exists():
                try:
                    _live_cortex.load(path)
                except Exception:
                    pass
        return _live_cortex


def live_cortex(bus: Optional[EventBus] = None) -> JeevesCortex:
    """Alias used by GameForge CLI / genesis."""
    return get_live(bus)


def get_control() -> Optional[ControlSurface]:
    return _live_control


def attach(bus: EventBus) -> JeevesCortex:
    cortex = get_live(bus)
    cortex._bus = bus
    bus.subscribe("*", cortex._on_event)
    return cortex


def status() -> dict[str, Any]:
    if _live_cortex is None:
        return {"live": False, "events_captured": 0}
    stats = _live_cortex.stats()
    stats["live"] = True
    return stats


def live_jeeves():
    """One Jeeves bound to the live cortex (CLI plan / cockpit)."""
    global _JEEVES
    from skeleton.jeeves.core import Jeeves
    with _LOCK:
        if _JEEVES is None:
            j = Jeeves()
            j.cortex = get_live()
            _JEEVES = j
        return _JEEVES


def persist() -> dict:
    cortex = get_live()
    saver = getattr(cortex, "save", None)
    if not callable(saver):
        return {"saved": False, "reason": "cortex_stub"}
    path = own_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return saver(path)


def reset_live(*, wipe_disk: bool = False) -> None:
    global _live_cortex, _live_control, _JEEVES
    with _LOCK:
        path = own_path()
        if wipe_disk and path.exists():
            path.unlink()
        _live_cortex = None
        _live_control = None
        _JEEVES = None
