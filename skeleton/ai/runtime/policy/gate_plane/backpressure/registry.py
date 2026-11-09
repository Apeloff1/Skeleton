"""Provider registry — how the API layer hands pressure signals to the gate plane.

``skeleton.gate_plane`` is domain/application code and must not import
``skeleton.api`` (enforced by ``scripts/check_architecture_boundaries.py``).
So instead of the gate plane importing Backend's Pack H helper, the API
composition root *registers* it (a downward dependency)::

    # in skeleton/api (Backend / app wiring), once at startup:
    from skeleton.api.pack_h.admit_pressure import snapshot
    from skeleton.api.admit_write import get_default_gate
    from skeleton.gate_plane.backpressure import register_adaptive_gate, register_pressure_provider

    register_pressure_provider(snapshot)          # Pack H, schema_version 1
    register_adaptive_gate(get_default_gate())    # fallback signal

Until something registers, :class:`PackHSource` reports unavailable and the
fallback chain moves on — the gate plane never blocks on Pack H landing.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

PressureProvider = Callable[..., Any]

_lock = threading.Lock()
_provider: Optional[PressureProvider] = None
_gate: Any = None


def register_pressure_provider(fn: Optional[PressureProvider]) -> None:
    """Register ``fn(tenant_id=None) -> snapshot`` (or ``None`` to clear)."""
    if fn is not None and not callable(fn):
        raise TypeError("pressure provider must be callable")
    global _provider
    with _lock:
        _provider = fn


def pressure_provider() -> Optional[PressureProvider]:
    with _lock:
        return _provider


def register_adaptive_gate(gate: Any) -> None:
    """Register the process AdaptiveGate used as the fallback signal (``None`` clears)."""
    if gate is not None and not callable(getattr(gate, "stats", None)):
        raise TypeError("adaptive gate must expose stats()")
    global _gate
    with _lock:
        _gate = gate


def adaptive_gate() -> Any:
    with _lock:
        return _gate


def reset_registry_for_tests() -> None:
    register_pressure_provider(None)
    register_adaptive_gate(None)


__all__ = [
    "PressureProvider",
    "adaptive_gate",
    "pressure_provider",
    "register_adaptive_gate",
    "register_pressure_provider",
    "reset_registry_for_tests",
]
