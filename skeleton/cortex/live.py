"""Process-lived Jeeves — the same neocortex across HTTP, CLI, genesis.

Every `JeevesCortex()` in the HTTP routes was a new amnesiac. Train then
run must be the same organism. This module is the singleton: one cortex,
one Jeeves, optional disk persist at $SKELETON_OWN (default
`.skeleton/own.json`). Tests stay hermetic via `GameForgeRun()` (not live)
or `reset_live()`.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

_LOCK = threading.RLock()
_CORTEX = None
_JEEVES = None


def own_path() -> Path:
    raw = os.environ.get("SKELETON_OWN")
    if raw:
        return Path(raw)
    return Path(".skeleton") / "own.json"


def live_cortex():
    """The neocortex. Loads disk on first touch."""
    global _CORTEX
    from skeleton.cortex.neocortex import JeevesCortex
    with _LOCK:
        if _CORTEX is None:
            _CORTEX = JeevesCortex()
            path = own_path()
            if path.exists():
                _CORTEX.load(path)
        return _CORTEX


def live_jeeves():
    global _JEEVES
    from skeleton.jeeves.core import Jeeves
    with _LOCK:
        if _JEEVES is None:
            j = Jeeves()
            j.cortex = live_cortex()
            _JEEVES = j
        return _JEEVES


def persist() -> dict:
    cortex = live_cortex()
    return cortex.save(own_path())


def reset_live(*, wipe_disk: bool = False) -> None:
    """Drop the process singleton. Tests only."""
    global _CORTEX, _JEEVES
    with _LOCK:
        path = own_path()
        if wipe_disk and path.exists():
            path.unlink()
        _CORTEX = None
        _JEEVES = None