"""Non-owning compatibility facade for the canonical implementation at skeleton.automation.shift_supervisor.model_gateway.

This AI-tree surface deliberately owns no provider credentials or network policy.
Attribute fallback preserves compatibility while the legacy owner remains authoritative
until explicit migration cutover.
"""
from __future__ import annotations

import skeleton.automation.shift_supervisor.model_gateway as _impl
from skeleton.automation.shift_supervisor.model_gateway import *  # noqa: F401,F403

__all__ = tuple(getattr(_impl, "__all__", tuple(name for name in dir(_impl) if not name.startswith("_"))))


def __getattr__(name: str):
    return getattr(_impl, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_impl)))
