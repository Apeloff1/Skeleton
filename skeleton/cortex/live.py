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
_LAST_LOAD: dict[str, Any] = {"ok": True, "loaded": False, "reason": "uninitialized"}


class CortexPersistenceError(RuntimeError):
    """Raised when configured durable cortex state cannot be restored."""


def configured_own_path() -> Optional[Path]:
    """Return the explicitly configured persistence path, if any.

    ``SKELETON_OWN`` is the opt-in signal that a process is expected to own
    durable cortex state.  The legacy fallback path remains available through
    :func:`own_path`, but callers that decide whether multiple runtime surfaces
    may share the process singleton should key off this explicit configuration
    instead of an incidental ``.skeleton`` file.
    """
    raw = os.environ.get("SKELETON_OWN")
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    return Path(raw)


def persistence_configured() -> bool:
    """Whether durable cortex ownership was explicitly configured."""
    return configured_own_path() is not None


def own_path() -> Path:
    configured = configured_own_path()
    if configured is not None:
        return configured
    return Path(".skeleton") / "own.json"


def get_live(bus: Optional[EventBus] = None) -> JeevesCortex:
    """Get or create the process-lived cortex singleton (API wiring name).

    Disk restore is opt-in. Only an explicit ``SKELETON_OWN`` path is loaded,
    so unconfigured genesis twins stay fresh. Configured restore is fail-closed:
    a corrupt or unreadable snapshot does not boot a silent empty organism.
    """
    global _live_cortex, _live_control, _LAST_LOAD
    with _LOCK:
        if _live_cortex is None:
            cortex = JeevesCortex(bus=bus or EventBus())
            control = ControlSurface(cortex, bus=bus)
            if persistence_configured():
                path = own_path()
                if path.exists():
                    try:
                        cortex.load(path)
                    except Exception as exc:
                        _LAST_LOAD = {
                            "ok": False,
                            "loaded": False,
                            "path": str(path),
                            "reason": "restore_failed",
                        }
                        raise CortexPersistenceError(
                            "failed to restore configured cortex state"
                        ) from exc
                    _LAST_LOAD = {"ok": True, "loaded": True, "path": str(path)}
                else:
                    _LAST_LOAD = {
                        "ok": True,
                        "loaded": False,
                        "path": str(path),
                        "reason": "missing_snapshot",
                    }
            else:
                _LAST_LOAD = {
                    "ok": True,
                    "loaded": False,
                    "reason": "persistence_not_configured",
                }
            _live_cortex = cortex
            _live_control = control
        return _live_cortex


def live_cortex(bus: Optional[EventBus] = None) -> JeevesCortex:
    """Return the process singleton and bind it to the caller's bus."""
    global _live_control
    with _LOCK:
        cortex = get_live(bus)
        if bus is not None:
            cortex._bus = bus
            _live_control = ControlSurface(cortex, bus=bus)
        return cortex


def get_control() -> Optional[ControlSurface]:
    return _live_control


def attach(bus: EventBus) -> JeevesCortex:
    """Bind the live cortex to ``bus`` and subscribe when it has an observer."""
    cortex = live_cortex(bus)
    observer = getattr(cortex, "_on_event", None)
    if callable(observer):
        bus.subscribe("*", observer)
    return cortex


def status() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "persistence_configured": persistence_configured(),
        "last_load": dict(_LAST_LOAD),
    }
    if _live_cortex is None:
        payload.update({"live": False, "events_captured": 0})
        return payload
    stats = _live_cortex.status()
    if _live_control is not None:
        control_stats = getattr(_live_control, "stats", None)
        if callable(control_stats):
            stats["control"] = control_stats()
    stats.update(payload)
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
    saved = saver(path)
    saved["saved"] = True
    saved["configured"] = persistence_configured()
    return saved


def reset_live(*, wipe_disk: bool = False) -> None:
    global _live_cortex, _live_control, _JEEVES, _LAST_LOAD
    with _LOCK:
        path = own_path()
        if wipe_disk and path.exists():
            path.unlink()
        _live_cortex = None
        _live_control = None
        _JEEVES = None
        _LAST_LOAD = {"ok": True, "loaded": False, "reason": "reset"}
