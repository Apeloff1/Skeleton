"""Legacy compatibility shim for the relocated shift-supervisor model gateway.

Provider credentials, network transport, and execution behavior are owned only by
`skeleton.ai.build.shift_supervisor.model_gateway`. This module preserves the historical import path without
creating a second provider surface.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_impl = import_module("skeleton.ai.build.shift_supervisor.model_gateway")

__all__ = tuple(
    name
    for name in dir(_impl)
    if not name.startswith("_")
)


def __getattr__(name: str) -> Any:
    return getattr(_impl, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_impl)))
