"""Realtime hub bounds (Jenkins S2-1/S2-4/S2-5) read from the environment.

Moved out of ``skeleton/api/server.py`` so the server keeps a single call line
(#4256 exact-line allowlist). Env overrides are documented in
``docs/engineering/PERFORMANCE_BUDGETS.md``.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict


def _num(name: str, default: Any, cast: Callable[[str], Any] = int) -> Any:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = cast(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def realtime_limits_from_env() -> Dict[str, Any]:
    """Keyword arguments for :class:`RealtimeHub` bounds; invalid env -> default."""
    return {
        "presence_meta_max_bytes": _num(
            "SKELETON_REALTIME_PRESENCE_META_MAX_BYTES", 2048
        ),
        "presence_max_members_per_scope": _num(
            "SKELETON_REALTIME_PRESENCE_MAX_MEMBERS", 256
        ),
        "max_streams_per_principal": _num(
            "SKELETON_REALTIME_MAX_STREAMS_PER_PRINCIPAL", 8
        ),
        "max_stream_lifetime_s": _num(
            "SKELETON_REALTIME_MAX_STREAM_LIFETIME_S", 900.0, float
        ),
    }


__all__ = ["realtime_limits_from_env"]
