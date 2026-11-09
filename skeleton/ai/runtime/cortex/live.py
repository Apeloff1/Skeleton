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


def initialize_persisted_production(*, epochs: int = 1) -> dict[str, Any]:
    """Operator-only FIRST-BOOT training of this exact app-owned Jeeves.

    This runs *inside* the already initialized app process and is never a
    scratch checkpoint substitution for an existing serving model. It must
    execute while the compiled app is in private maintenance/bootstrap mode,
    before user requests are admitted. Existing production state is immutable.
    The app must restart and restore the just-persisted state before a
    separate specialization session can attest it.
    """
    with _LOCK:
        if os.environ.get("SKELETON_JEEVES_BOOTSTRAP", "").strip() != "1":
            raise CortexPersistenceError("first-boot production training requires explicit operator bootstrap mode")
        if type(epochs) is not int or epochs != 1:
            raise CortexPersistenceError("first-boot production bootstrap is limited to exactly one epoch")
        if not persistence_configured():
            raise CortexPersistenceError("first-boot production training requires SKELETON_OWN")
        if _live_cortex is None or _LAST_LOAD.get("loaded") or _LAST_LOAD.get("reason") != "missing_snapshot":
            raise CortexPersistenceError("bootstrap requires initialized app-owned Jeeves with no restored state")
        target = own_path()
        if target.is_symlink() or target.exists():
            raise CortexPersistenceError("never initialize over an existing production snapshot")
        if not target.parent.is_dir():
            raise CortexPersistenceError("configure an existing private production state directory first")
        if getattr(_live_cortex.transformer, "steps", 0) != 0:
            raise CortexPersistenceError("bootstrap transformer must be new, not previously trained")
        original_steps = _live_cortex.transformer.steps
        result = _live_cortex.train(epochs=1, auto_surpass=False)
        if _live_cortex.transformer.steps <= original_steps:
            raise CortexPersistenceError("bootstrap executed without actual production model weight steps")
        saved = persist()
        if not target.is_file():
            raise CortexPersistenceError("trained production checkpoint was not persisted")
        return {
            "status": "production_first_boot_checkpoint_created_restart_required",
            "production_model_trained": True,
            "training_steps": int(_live_cortex.transformer.steps),
            "model_file": str(target.resolve()),
            "snapshot_restored_in_current_process": False,
            "ready_to_attest": False,
            "requires_restart": True,
            "separate_game_specialization_not_started": True,
            "automatic_promotion": False,
        }


def attest_training_checkpoint(destination: str | Path) -> dict[str, Any]:
    """Operator seam to attest the *already running* Jeeves in this process.

    Must be invoked from the compiled app's privileged local operator surface.
    Never starts a second cortex or creates a substitute model. Call persist()
    first if the live weights legitimately changed since the loaded snapshot.
    """
    with _LOCK:
        if _live_cortex is None or not _LAST_LOAD.get("loaded"):
            raise CortexPersistenceError("no restored production Jeeves is running to attest")
        if not persistence_configured():
            raise CortexPersistenceError("SKELETON_OWN is required for production attestation")
        from skeleton.ai.training.jeeves_production_readiness import attest_running_cortex
        return attest_running_cortex(_live_cortex, Path(destination))


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
